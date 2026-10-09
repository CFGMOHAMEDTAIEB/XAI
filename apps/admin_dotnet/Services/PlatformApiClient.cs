using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.Logging.Abstractions;
using XaiCompress.Admin.Models;

namespace XaiCompress.Admin.Services;

public sealed class AdminApiAuthorizationException(HttpStatusCode statusCode)
    : Exception("The admin session is missing, expired, or unauthorized.")
{
    public HttpStatusCode StatusCode { get; } = statusCode;
}
public sealed class AdminMfaRequiredException() : Exception("An authenticator code is required.");
public sealed class AdminEnrollmentRequiredException() : Exception("Authenticator enrollment is required.");
public sealed class AdminRecoveryInvalidException() : Exception("The recovery authorization is invalid or expired.");

public sealed record AdminRefreshHandoff(string AccessToken, string RefreshToken);

public sealed class AdminRefreshCoordinator
{
    private sealed record Entry(AdminRefreshHandoff Session, DateTimeOffset ExpiresAt);
    private readonly ConcurrentDictionary<string, Entry> _rotations = new();

    public void Remember(string previousRefreshToken, string accessToken, string refreshToken)
    {
        var now = DateTimeOffset.UtcNow;
        foreach (var item in _rotations.Where(x => x.Value.ExpiresAt <= now))
            _rotations.TryRemove(item.Key, out _);
        _rotations[Fingerprint(previousRefreshToken)] =
            new Entry(new AdminRefreshHandoff(accessToken, refreshToken), now.AddMinutes(5));
    }

    public bool TryGet(string previousRefreshToken, out AdminRefreshHandoff? handoff)
    {
        handoff = null;
        if (!_rotations.TryGetValue(Fingerprint(previousRefreshToken), out var entry)) return false;
        if (entry.ExpiresAt <= DateTimeOffset.UtcNow)
        {
            _rotations.TryRemove(Fingerprint(previousRefreshToken), out _);
            return false;
        }
        handoff = entry.Session;
        return true;
    }

    private static string Fingerprint(string token) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(token)));
}

public sealed class PlatformApiClient
{
    private readonly HttpClient _http;
    private readonly AdminSession _session;
    private readonly AdminRefreshCoordinator _refreshCoordinator;
    private readonly ILogger<PlatformApiClient> _logger;
    // Blazor can briefly have an old and a new circuit for the same browser tab.
    // A process-wide gate prevents those circuits from consuming the same rotating
    // refresh token concurrently. The encrypted browser snapshot transfers the winner.
    private static readonly SemaphoreSlim RefreshGate = new(1, 1);
    private string? _mfaToken, _enrollmentToken, _enrollmentId;

    public PlatformApiClient(HttpClient http, AdminSession session,
        AdminRefreshCoordinator? refreshCoordinator = null, ILogger<PlatformApiClient>? logger = null)
    {
        _http = http;
        _session = session;
        _refreshCoordinator = refreshCoordinator ?? new AdminRefreshCoordinator();
        _logger = logger ?? NullLogger<PlatformApiClient>.Instance;
    }

    public async Task LoginAsync(string email, string password, string? totpCode = null)
    {
        _logger.LogInformation("Admin login started hasTotpCode={HasTotpCode}", !string.IsNullOrWhiteSpace(totpCode));
        await _session.BeginAuthenticationAsync();
        ClearPending();
        using var loginResponse = await _http.PostAsJsonAsync(
            "/auth/login", new { email, password, totp_code = totpCode });

        if (loginResponse.StatusCode is HttpStatusCode.Unauthorized)
        {
            using var error = await JsonDocument.ParseAsync(await loginResponse.Content.ReadAsStreamAsync());
            var detail = error.RootElement.GetProperty("detail");
            if (detail.ValueKind == JsonValueKind.Object && detail.TryGetProperty("mfa_token", out var challenge))
            {
                _mfaToken = challenge.GetString();
                _session.RequireMfa();
                _logger.LogInformation("Admin login challenge result=MfaRequired statusCode={StatusCode}",
                    (int)loginResponse.StatusCode);
                throw new AdminMfaRequiredException();
            }
            throw new AdminApiAuthorizationException(loginResponse.StatusCode);
        }
        if (loginResponse.StatusCode is HttpStatusCode.Forbidden)
            throw new AdminApiAuthorizationException(loginResponse.StatusCode);

        loginResponse.EnsureSuccessStatusCode();
        var token = await loginResponse.Content.ReadFromJsonAsync<TokenEnvelope>()
            ?? throw new InvalidOperationException("The backend did not return an access token.");
        if (string.IsNullOrWhiteSpace(token.AccessToken)) throw new InvalidOperationException("The backend did not return an access token.");

        if (token.EnrollmentRequired)
        {
            using var accountRequest = CreateAuthorizedRequest(HttpMethod.Get, "/auth/me", token.AccessToken);
            using var accountResponse = await _http.SendAsync(accountRequest);
            accountResponse.EnsureSuccessStatusCode();
            using var account = await JsonDocument.ParseAsync(await accountResponse.Content.ReadAsStreamAsync());
            if (!string.Equals(account.RootElement.GetProperty("role").GetString(), "admin", StringComparison.OrdinalIgnoreCase))
                throw new AdminApiAuthorizationException(HttpStatusCode.Forbidden);
            _enrollmentToken = token.AccessToken;
            _session.RequireMfa();
            using var start = CreateAuthorizedRequest(HttpMethod.Post, "/auth/authenticator/enroll/start", _enrollmentToken);
            start.Content = JsonContent.Create(new { });
            using var startResponse = await _http.SendAsync(start);
            startResponse.EnsureSuccessStatusCode();
            using var pending = await JsonDocument.ParseAsync(await startResponse.Content.ReadAsStreamAsync());
            _enrollmentId = pending.RootElement.GetProperty("enrollment_id").GetString();
            throw new AdminEnrollmentRequiredException();
        }
        await EstablishAdminSessionAsync(token);
    }

    public async Task VerifyMfaAsync(string code)
    {
        if (string.IsNullOrEmpty(_mfaToken)) throw new AdminApiAuthorizationException(HttpStatusCode.Unauthorized);
        using var response = await _http.PostAsJsonAsync("/auth/login/mfa/verify", new { mfa_token = _mfaToken, code });
        if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.BadRequest)
            throw new AdminApiAuthorizationException(HttpStatusCode.Unauthorized);
        response.EnsureSuccessStatusCode();
        var token = await response.Content.ReadFromJsonAsync<TokenEnvelope>() ?? throw new InvalidOperationException("Missing token.");
        _logger.LogInformation(
            "Admin MFA verification succeeded statusCode={StatusCode} hasAccessToken={HasAccessToken} hasRefreshToken={HasRefreshToken}",
            (int)response.StatusCode, !string.IsNullOrWhiteSpace(token.AccessToken), !string.IsNullOrWhiteSpace(token.RefreshToken));
        await EstablishAdminSessionAsync(token);
        ClearPending();
    }

    public async Task ConfirmEnrollmentAsync(string code)
    {
        if (string.IsNullOrEmpty(_enrollmentToken) || string.IsNullOrEmpty(_enrollmentId))
            throw new AdminApiAuthorizationException(HttpStatusCode.Unauthorized);
        using var request = CreateAuthorizedRequest(HttpMethod.Post, "/auth/authenticator/enroll/confirm", _enrollmentToken);
        request.Content = JsonContent.Create(new { enrollment_id = _enrollmentId, code });
        using var response = await _http.SendAsync(request);
        if (response.StatusCode is HttpStatusCode.BadRequest or HttpStatusCode.Unauthorized)
            throw new AdminApiAuthorizationException(HttpStatusCode.Unauthorized);
        response.EnsureSuccessStatusCode();
        var token = await response.Content.ReadFromJsonAsync<TokenEnvelope>() ?? throw new InvalidOperationException("Missing token.");
        await EstablishAdminSessionAsync(token);
        ClearPending();
    }

    public void ClearPending() { _mfaToken = null; _enrollmentToken = null; _enrollmentId = null; }

    public async Task RequestPasswordResetAsync(string email)
    {
        using var response = await _http.PostAsJsonAsync("/auth/password/forgot", new { identifier = email });
        response.EnsureSuccessStatusCode();
    }

    public async Task<string> VerifyPasswordResetCodeAsync(string email, string code)
    {
        using var response = await _http.PostAsJsonAsync("/auth/password/verify-code", new { identifier = email, code });
        if (response.StatusCode == HttpStatusCode.BadRequest) throw new AdminRecoveryInvalidException();
        response.EnsureSuccessStatusCode();
        var result = await response.Content.ReadFromJsonAsync<PasswordResetAuthorization>();
        if (string.IsNullOrWhiteSpace(result?.ResetToken)) throw new InvalidOperationException("Missing reset authorization.");
        return result.ResetToken;
    }

    public async Task ResetPasswordAsync(string resetToken, string newPassword)
    {
        using var response = await _http.PostAsJsonAsync("/auth/password/reset", new { reset_token = resetToken, new_password = newPassword });
        if (response.StatusCode == HttpStatusCode.BadRequest) throw new AdminRecoveryInvalidException();
        response.EnsureSuccessStatusCode();
    }

    private async Task EstablishAdminSessionAsync(TokenEnvelope token)
    {
        if (string.IsNullOrWhiteSpace(token.AccessToken) || string.IsNullOrWhiteSpace(token.RefreshToken))
            throw new InvalidOperationException("The backend did not return a complete administrator session.");
        using var validation = CreateAuthorizedRequest(HttpMethod.Get, "/admin/stats", token.AccessToken);
        using var validationResponse = await _http.SendAsync(validation);
        if (validationResponse.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
            throw new AdminApiAuthorizationException(validationResponse.StatusCode);
        validationResponse.EnsureSuccessStatusCode();
        _logger.LogInformation(
            "Admin authorization validation succeeded statusCode={StatusCode} hasAccessToken={HasAccessToken} hasRefreshToken={HasRefreshToken}",
            (int)validationResponse.StatusCode, !string.IsNullOrWhiteSpace(token.AccessToken), !string.IsNullOrWhiteSpace(token.RefreshToken));
        await _session.SetTokenAsync(token.AccessToken, token.RefreshToken, AdminSessionReason.LoginSucceeded);
        _logger.LogInformation("Admin login completed state={State} revision={Revision}", _session.State, _session.Revision);
    }

    public async Task LogoutAsync()
    {
        ClearPending();
        var refreshToken = _session.RefreshToken;
        await _session.SignOutAsync();
        if (string.IsNullOrEmpty(refreshToken)) return;
        try { using var response = await _http.PostAsJsonAsync("/auth/logout", new { refresh_token = refreshToken }); }
        catch (HttpRequestException) { /* Local session has already been cleared. */ }
        catch (OperationCanceledException) { /* Finite timeout; local logout remains complete. */ }
    }

    public async Task<bool> IsHealthyAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            using var response = await _http.GetAsync("/health", cancellationToken);
            return response.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    public Task<DashboardStats> GetDashboardAsync() => GetProtectedAsync<DashboardStats>("/admin/stats");
    public async Task<IReadOnlyList<UserSummary>> GetUsersAsync() => await GetProtectedAsync<List<UserSummary>>("/admin/users");
    public async Task<IReadOnlyList<CompressionJob>> GetJobsAsync() => await GetProtectedAsync<List<CompressionJob>>("/admin/jobs");
    public async Task<IReadOnlyList<AuditEvent>> GetAuditAsync() => await GetProtectedAsync<List<AuditEvent>>("/admin/audit");
    public Task<UserDetails> GetUserAsync(int id) => GetProtectedAsync<UserDetails>($"/admin/users/{id}");
    public Task CreateUserAsync(string email, string fullName, string role) =>
        SendProtectedMutationAsync(HttpMethod.Post, "/admin/users", new { email, full_name = fullName, role });
    public Task UpdateUserAsync(int id, string? role, string? status) =>
        SendProtectedMutationAsync(HttpMethod.Patch, $"/admin/users/{id}", new { role, status });
    public Task RevokeRefreshSessionsAsync(int id) =>
        SendProtectedMutationAsync(HttpMethod.Post, $"/admin/users/{id}/revoke-refresh-sessions", new { });
    public Task ResetUserMfaAsync(int id) =>
        SendProtectedMutationAsync(HttpMethod.Post, $"/admin/users/{id}/reset-mfa", new { });
    public Task<ScannerStatus> GetScannerAsync() => GetProtectedAsync<ScannerStatus>("/admin/security/scanner");
    public Task<EmailConfiguration> GetEmailConfigurationAsync() => GetProtectedAsync<EmailConfiguration>("/admin/email/configuration");
    public async Task<IReadOnlyList<AuthenticatorDevice>> GetAuthenticatorDevicesAsync() => await GetProtectedAsync<List<AuthenticatorDevice>>("/admin/authenticator/devices");
    public async Task<IReadOnlyList<AuthenticatorHistory>> GetAuthenticatorHistoryAsync() => await GetProtectedAsync<List<AuthenticatorHistory>>("/admin/authenticator/history");
    public async Task<IReadOnlyList<RecoveryCodeSummary>> GetRecoveryCodeSummariesAsync() => await GetProtectedAsync<List<RecoveryCodeSummary>>("/admin/authenticator/recovery");
    public Task RevokeAuthenticatorDeviceAsync(string deviceId) =>
        SendProtectedMutationAsync(HttpMethod.Post,
            $"/admin/authenticator/devices/{Uri.EscapeDataString(deviceId)}/revoke", new { });
    public async Task<IReadOnlyList<AdminShare>> GetSharesAsync() => await GetProtectedAsync<List<AdminShare>>("/admin/shares");
    public Task RevokeShareAsync(int id) =>
        SendProtectedMutationAsync(HttpMethod.Post, $"/admin/shares/{id}/revoke", new { });
    public Task<IReadOnlyList<SecurityIncident>> GetIncidentsAsync() => Task.FromResult<IReadOnlyList<SecurityIncident>>([]);
    public Task<IReadOnlyList<QuarantinedFile>> GetQuarantineAsync() => Task.FromResult<IReadOnlyList<QuarantinedFile>>([]);

    public async Task<IReadOnlyList<ServiceHealth>> GetHealthAsync()
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        var cancellationToken = timeout.Token;
        var now = DateTimeOffset.UtcNow;
        var result = new List<ServiceHealth>();
        void Add(string name, string status) => result.Add(new ServiceHealth(name, status, 0, "Prerequisite check", now));

        var backendReady = await IsHealthyAsync(cancellationToken);
        Add("Backend", backendReady ? "Ready" : "Unavailable");
        try
        {
            await GetProtectedAsync<DashboardStats>("/admin/stats", cancellationToken);
            Add("Database", "Ready");
        }
        catch (AdminApiAuthorizationException) { throw; }
        catch (Exception) { Add("Database", "Unavailable"); }

        try
        {
            var scanner = await GetProtectedAsync<ScannerStatus>("/admin/security/scanner", cancellationToken);
            Add("ClamAV", scanner.Clamav == "operational" ? "Ready" : "Unavailable");
            Add("YARA", scanner.Yara == "operational" ? "Ready" : "Unavailable");
        }
        catch (AdminApiAuthorizationException) { throw; }
        catch (Exception) { Add("ClamAV", "Unavailable"); Add("YARA", "Unavailable"); }

        try
        {
            var email = await GetProtectedAsync<EmailConfiguration>("/admin/email/configuration", cancellationToken);
            Add("Email configuration", email.Configured ? "Configured" : "Not configured");
        }
        catch (AdminApiAuthorizationException) { throw; }
        catch (Exception) { Add("Email configuration", "Unavailable"); }
        return result;
    }

    private async Task<T> GetProtectedAsync<T>(string path, CancellationToken cancellationToken = default)
    {
        var token = _session.AccessToken;
        if (string.IsNullOrWhiteSpace(token)) throw new AdminApiAuthorizationException(HttpStatusCode.Unauthorized);
        using var request = CreateAuthorizedRequest(HttpMethod.Get, path, token);
        using var response = await _http.SendAsync(request, cancellationToken);
        if (response.StatusCode == HttpStatusCode.Unauthorized)
        {
            if (!await TryRefreshAsync(token, cancellationToken))
                throw new AdminApiAuthorizationException(HttpStatusCode.Unauthorized);
            var retryToken = _session.AccessToken!;
            var retryRefreshToken = _session.RefreshToken;
            var retryRevision = _session.Revision;
            using var retry = CreateAuthorizedRequest(HttpMethod.Get, path, retryToken);
            using var retryResponse = await _http.SendAsync(retry, cancellationToken);
            return await ReadProtectedResponseAsync<T>(retryResponse, cancellationToken,
                retryRevision, retryToken, retryRefreshToken);
        }
        return await ReadProtectedResponseAsync<T>(response, cancellationToken);
    }

    private async Task SendProtectedMutationAsync(HttpMethod method, string path, object body)
    {
        var token = _session.AccessToken;
        if (string.IsNullOrWhiteSpace(token)) throw new AdminApiAuthorizationException(HttpStatusCode.Unauthorized);
        using var request = CreateAuthorizedRequest(method, path, token);
        request.Content = JsonContent.Create(body);
        using var response = await _http.SendAsync(request);
        if (response.StatusCode == HttpStatusCode.Unauthorized)
        {
            if (!await TryRefreshAsync(token, CancellationToken.None))
                throw new AdminApiAuthorizationException(HttpStatusCode.Unauthorized);
            var retryToken = _session.AccessToken!;
            var retryRefreshToken = _session.RefreshToken;
            var retryRevision = _session.Revision;
            using var retry = CreateAuthorizedRequest(method, path, retryToken);
            retry.Content = JsonContent.Create(body);
            using var retryResponse = await _http.SendAsync(retry);
            await EnsureMutationResponseAsync(retryResponse, retryRevision, retryToken, retryRefreshToken);
            return;
        }
        await EnsureMutationResponseAsync(response);
    }

    private async Task EnsureMutationResponseAsync(HttpResponseMessage response, long? requestRevision = null,
        string? requestAccessToken = null, string? requestRefreshToken = null)
    {
        if (response.StatusCode == HttpStatusCode.Unauthorized)
        {
            await _session.ExpireIfCurrentAsync(requestRevision ?? _session.Revision,
                requestAccessToken ?? _session.AccessToken, requestRefreshToken ?? _session.RefreshToken,
                AdminSessionReason.RetryRejected);
            throw new AdminApiAuthorizationException(HttpStatusCode.Unauthorized);
        }
        if (response.StatusCode == HttpStatusCode.Forbidden)
            throw new AdminApiAuthorizationException(HttpStatusCode.Forbidden);
        response.EnsureSuccessStatusCode();
    }

    private async Task<T> ReadProtectedResponseAsync<T>(HttpResponseMessage response, CancellationToken cancellationToken,
        long? requestRevision = null, string? requestAccessToken = null, string? requestRefreshToken = null)
    {
        if (response.StatusCode == HttpStatusCode.Unauthorized)
        {
            await _session.ExpireIfCurrentAsync(requestRevision ?? _session.Revision,
                requestAccessToken ?? _session.AccessToken, requestRefreshToken ?? _session.RefreshToken,
                AdminSessionReason.RetryRejected);
            throw new AdminApiAuthorizationException(HttpStatusCode.Unauthorized);
        }
        if (response.StatusCode == HttpStatusCode.Forbidden)
            throw new AdminApiAuthorizationException(HttpStatusCode.Forbidden);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<T>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("The backend returned an empty response.");
    }

    private async Task<bool> TryRefreshAsync(string previousToken, CancellationToken cancellationToken)
    {
        await RefreshGate.WaitAsync(cancellationToken);
        try
        {
            if (_session.AccessToken != previousToken) return _session.IsAuthenticated;
            var revisionAtStart = _session.Revision;
            var refreshToken = _session.RefreshToken;
            if (string.IsNullOrWhiteSpace(refreshToken))
            {
                await _session.ExpireIfCurrentAsync(revisionAtStart, previousToken, refreshToken,
                    AdminSessionReason.MissingRefreshToken);
                return false;
            }
            if (_refreshCoordinator.TryGet(refreshToken, out var coordinated) && coordinated is not null)
            {
                await _session.SetTokenAsync(coordinated.AccessToken, coordinated.RefreshToken,
                    AdminSessionReason.AdoptedNewerSession);
                _logger.LogInformation("Admin refresh adopted process handoff revision={Revision}", _session.Revision);
                return true;
            }
            if (await _session.TryAdoptNewerStoredSessionAsync(refreshToken)) return true;
            _session.BeginRefresh();
            var refreshRevision = _session.Revision;
            _logger.LogInformation(
                "Admin refresh started revision={Revision} hasAccessToken={HasAccessToken} hasRefreshToken={HasRefreshToken}",
                refreshRevision, !string.IsNullOrWhiteSpace(_session.AccessToken),
                !string.IsNullOrWhiteSpace(_session.RefreshToken));
            using var response = await _http.PostAsJsonAsync("/auth/refresh", new { refresh_token = refreshToken }, cancellationToken);
            if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
            {
                if (_refreshCoordinator.TryGet(refreshToken, out coordinated) && coordinated is not null)
                {
                    await _session.SetTokenAsync(coordinated.AccessToken, coordinated.RefreshToken,
                        AdminSessionReason.AdoptedNewerSession);
                    return true;
                }
                if (await _session.TryAdoptNewerStoredSessionAsync(refreshToken)) return true;
                var actuallyExpired = await _session.ExpireIfCurrentAsync(refreshRevision, previousToken, refreshToken,
                    AdminSessionReason.RefreshRejected);
                _logger.LogWarning(
                    "Admin refresh rejected statusCode={StatusCode} revision={Revision} finalState={State}",
                    (int)response.StatusCode, refreshRevision, _session.State);
                return !actuallyExpired && _session.IsAuthenticated;
            }
            response.EnsureSuccessStatusCode();
            var renewed = await response.Content.ReadFromJsonAsync<TokenEnvelope>(cancellationToken: cancellationToken);
            if (string.IsNullOrWhiteSpace(renewed?.AccessToken))
                throw new InvalidOperationException("The backend returned an incomplete refresh response.");
            // Some compatible identity providers rotate refresh tokens while others
            // only return a new access token. Never discard a still-valid refresh
            // token merely because the optional response field was omitted.
            var nextRefreshToken = renewed.RefreshToken ?? refreshToken;
            _refreshCoordinator.Remember(refreshToken, renewed.AccessToken, nextRefreshToken);
            await _session.SetTokenAsync(renewed.AccessToken, nextRefreshToken,
                AdminSessionReason.RefreshSucceeded);
            return true;
        }
        catch
        {
            // Network failures are retriable and must not be presented as an expired session.
            if (_session.State == AdminSessionState.Refreshing && !string.IsNullOrWhiteSpace(_session.AccessToken))
                _session.SetToken(_session.AccessToken, _session.RefreshToken, AdminSessionReason.RefreshSucceeded);
            throw;
        }
        finally { RefreshGate.Release(); }
    }

    private static HttpRequestMessage CreateAuthorizedRequest(HttpMethod method, string path, string token)
    {
        var request = new HttpRequestMessage(method, path);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return request;
    }

    private sealed record PasswordResetAuthorization([property: JsonPropertyName("reset_token")] string ResetToken);

    private sealed record TokenEnvelope([property: JsonPropertyName("access_token")] string AccessToken,
        [property: JsonPropertyName("refresh_token")] string? RefreshToken,
        [property: JsonPropertyName("enrollment_required")] bool EnrollmentRequired = false);
}
