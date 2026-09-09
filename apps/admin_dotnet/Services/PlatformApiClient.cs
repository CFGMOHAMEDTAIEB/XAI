using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json.Serialization;
using XaiCompress.Admin.Models;

namespace XaiCompress.Admin.Services;

public sealed class AdminApiAuthorizationException(HttpStatusCode statusCode)
    : Exception("The admin session is missing, expired, or unauthorized.")
{
    public HttpStatusCode StatusCode { get; } = statusCode;
}

public sealed class PlatformApiClient
{
    private readonly HttpClient _http;
    private readonly AdminSession _session;
    private readonly DemoAdminData _demo;
    private readonly bool _demoEnabled;

    public PlatformApiClient(HttpClient http, AdminSession session, DemoAdminData demo, IConfiguration configuration, IWebHostEnvironment environment)
    {
        _http = http;
        _session = session;
        _demo = demo;
        _demoEnabled = environment.IsDevelopment() && configuration.GetValue<bool>("PlatformApi:UseDemoFallback");
    }

    public async Task LoginAsync(string email, string password, string? totpCode = null)
    {
        using var loginResponse = await _http.PostAsJsonAsync(
            "/auth/login", new { email, password, totp_code = totpCode });

        if (loginResponse.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
            throw new AdminApiAuthorizationException(loginResponse.StatusCode);

        loginResponse.EnsureSuccessStatusCode();
        var token = await loginResponse.Content.ReadFromJsonAsync<TokenEnvelope>()
            ?? throw new InvalidOperationException("The backend did not return an access token.");

        // Verify the role before retaining the token in this Blazor circuit.
        using var validation = CreateAuthorizedRequest(HttpMethod.Get, "/admin/stats", token.AccessToken);
        using var validationResponse = await _http.SendAsync(validation);
        if (validationResponse.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
            throw new AdminApiAuthorizationException(validationResponse.StatusCode);
        validationResponse.EnsureSuccessStatusCode();

        _session.SetToken(token.AccessToken, token.RefreshToken);
    }

    public async Task LogoutAsync()
    {
        var refreshToken = _session.RefreshToken;
        _session.Clear();
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
    public Task<IReadOnlyList<SecurityIncident>> GetIncidentsAsync() => Task.FromResult<IReadOnlyList<SecurityIncident>>(_demoEnabled ? _demo.Incidents : []);
    public Task<IReadOnlyList<QuarantinedFile>> GetQuarantineAsync() => Task.FromResult<IReadOnlyList<QuarantinedFile>>(_demoEnabled ? _demo.Quarantine : []);

    public async Task<IReadOnlyList<ServiceHealth>> GetHealthAsync()
    {
        var apiHealthy = await IsHealthyAsync();
        return _demo.Health
            .Select(service => service.Name == "FastAPI"
                ? service with { Status = apiHealthy ? "Healthy" : "Unavailable", CheckedAt = DateTimeOffset.UtcNow }
                : _demoEnabled ? service : service with { Status = "Unknown", Version = "Unverified", LatencyMs = 0, CheckedAt = DateTimeOffset.UtcNow })
            .ToList();
    }

    private async Task<T> GetProtectedAsync<T>(string path)
    {
        if (!_session.IsAuthenticated)
            throw new AdminApiAuthorizationException(HttpStatusCode.Unauthorized);

        using var request = CreateAuthorizedRequest(HttpMethod.Get, path, _session.AccessToken!);
        using var response = await _http.SendAsync(request);
        if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
        {
            _session.Clear();
            throw new AdminApiAuthorizationException(response.StatusCode);
        }

        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<T>()
            ?? throw new InvalidOperationException($"The backend returned an empty response for {path}.");
    }

    private static HttpRequestMessage CreateAuthorizedRequest(HttpMethod method, string path, string token)
    {
        var request = new HttpRequestMessage(method, path);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return request;
    }

    private sealed record TokenEnvelope([property: JsonPropertyName("access_token")] string AccessToken,
        [property: JsonPropertyName("refresh_token")] string? RefreshToken);
}
