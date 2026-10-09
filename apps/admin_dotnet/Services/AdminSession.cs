using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.JSInterop;

namespace XaiCompress.Admin.Services;

public enum AdminSessionState
{
    SignedOut,
    Restoring,
    Authenticating,
    MfaRequired,
    Authenticated,
    Refreshing,
    Expired
}

public enum AdminSessionReason
{
    RestoreStarted,
    RestoreSucceeded,
    RestoreMissing,
    RestoreStorageFailure,
    LoginStarted,
    MfaRequired,
    LoginSucceeded,
    RefreshStarted,
    RefreshSucceeded,
    AdoptedNewerSession,
    RefreshRejected,
    RetryRejected,
    MissingRefreshToken,
    SignedOut
}

public sealed class AdminSession
{
    // ProtectedSessionStorage is shared by overlapping circuits in one browser tab.
    // Serializing mutations prevents an older circuit from deleting a newer snapshot.
    private static readonly SemaphoreSlim StorageMutationGate = new(1, 1);
    private readonly IAdminSessionStore? _storage;
    private readonly ILogger<AdminSession> _logger;
    private long _revision;

    public AdminSession(IAdminSessionStore? storage = null, ILogger<AdminSession>? logger = null)
    {
        _storage = storage;
        _logger = logger ?? NullLogger<AdminSession>.Instance;
    }

    public string? AccessToken { get; private set; }
    public string? RefreshToken { get; private set; }
    public AdminSessionState State { get; private set; } = AdminSessionState.SignedOut;
    public long Revision => Interlocked.Read(ref _revision);
    public bool IsAuthenticated => State is AdminSessionState.Authenticated or AdminSessionState.Refreshing
        && !string.IsNullOrWhiteSpace(AccessToken);
    public event Action? Changed;

    public void BeginAuthentication()
    {
        AccessToken = null;
        RefreshToken = null;
        Transition(AdminSessionState.Authenticating, AdminSessionReason.LoginStarted);
    }

    public void RequireMfa() => Transition(AdminSessionState.MfaRequired, AdminSessionReason.MfaRequired);
    public void BeginRefresh() => Transition(AdminSessionState.Refreshing, AdminSessionReason.RefreshStarted);

    public void SetToken(string token, string? refreshToken = null) =>
        SetToken(token, refreshToken, AdminSessionReason.LoginSucceeded);

    public void SetToken(string token, string? refreshToken, AdminSessionReason reason)
    {
        AccessToken = token;
        RefreshToken = refreshToken;
        Transition(AdminSessionState.Authenticated, reason);
    }

    public void Clear() => Clear(AdminSessionState.SignedOut, AdminSessionReason.SignedOut);

    public async Task RestoreAsync()
    {
        if (_storage is null || State != AdminSessionState.SignedOut) return;

        Transition(AdminSessionState.Restoring, AdminSessionReason.RestoreStarted);
        var revisionAtStart = Revision;
        try
        {
            var saved = await _storage.ReadAsync();
            if (Revision != revisionAtStart || State != AdminSessionState.Restoring)
            {
                LogDiscardedRestore(revisionAtStart);
                return;
            }

            if (!string.IsNullOrWhiteSpace(saved?.AccessToken) && !string.IsNullOrWhiteSpace(saved.RefreshToken))
                SetToken(saved.AccessToken, saved.RefreshToken, AdminSessionReason.RestoreSucceeded);
            else
                Transition(AdminSessionState.SignedOut, AdminSessionReason.RestoreMissing);
        }
        catch (Exception ex)
        {
            if (Revision != revisionAtStart || State != AdminSessionState.Restoring)
            {
                LogDiscardedRestore(revisionAtStart);
                return;
            }

            _logger.LogWarning("Admin session restore failed safely reason={Reason} errorType={ErrorType} revision={Revision}",
                AdminSessionReason.RestoreStorageFailure, ex.GetType().Name, revisionAtStart);
            Transition(AdminSessionState.SignedOut, AdminSessionReason.RestoreStorageFailure);
            // A corrupt or unreadable startup snapshot is not a genuine expiry.
            // Do not delete here: another overlapping circuit may already have replaced it.
        }
    }

    public async Task BeginAuthenticationAsync()
    {
        BeginAuthentication();
        var revision = Revision;
        if (_storage is null) return;
        await StorageMutationGate.WaitAsync();
        try
        {
            if (Revision != revision) return;
            try
            {
                await _storage.WriteAsync(new StoredAdminSession("", "", AuthenticationPending: true));
                _logger.LogInformation("Admin authentication marker saved revision={Revision}", revision);
            }
            catch (Exception ex) when (IsStorageException(ex))
            {
                _logger.LogWarning("Admin authentication marker save failed revision={Revision}", revision);
            }
        }
        finally { StorageMutationGate.Release(); }
    }

    public async Task SetTokenAsync(string token, string? refreshToken,
        AdminSessionReason reason = AdminSessionReason.LoginSucceeded)
    {
        SetToken(token, refreshToken, reason);
        var revision = Revision;
        if (_storage is null || string.IsNullOrWhiteSpace(refreshToken)) return;

        await StorageMutationGate.WaitAsync();
        try
        {
            if (Revision != revision || AccessToken != token || RefreshToken != refreshToken)
            {
                _logger.LogInformation(
                    "Admin session storage write discarded reason=StaleRevision startedRevision={StartedRevision} currentRevision={CurrentRevision}",
                    revision, Revision);
                return;
            }
            await _storage.WriteAsync(new StoredAdminSession(token, refreshToken));
            _logger.LogInformation(
                "Admin session storage saved revision={Revision} hasAccessToken={HasAccessToken} hasRefreshToken={HasRefreshToken}",
                revision, true, true);
        }
        catch (Exception ex) when (IsStorageException(ex))
        {
            _logger.LogWarning("Admin session storage save failed revision={Revision}", revision);
            // The authenticated in-memory circuit remains authoritative.
        }
        finally { StorageMutationGate.Release(); }
    }

    public async Task<bool> TryAdoptNewerStoredSessionAsync(string currentRefreshToken)
    {
        if (_storage is null) return false;
        var revisionAtStart = Revision;
        await StorageMutationGate.WaitAsync();
        try
        {
            var saved = await _storage.ReadAsync();
            if (Revision != revisionAtStart || !string.Equals(RefreshToken, currentRefreshToken, StringComparison.Ordinal))
                return false;
            if (string.IsNullOrWhiteSpace(saved?.AccessToken) || string.IsNullOrWhiteSpace(saved.RefreshToken)
                || string.Equals(saved.RefreshToken, currentRefreshToken, StringComparison.Ordinal)) return false;
            SetToken(saved.AccessToken, saved.RefreshToken, AdminSessionReason.AdoptedNewerSession);
            return true;
        }
        catch (Exception ex) when (IsStorageException(ex)) { return false; }
        finally { StorageMutationGate.Release(); }
    }

    public Task SignOutAsync() => ClearStoredSnapshotAsync(AdminSessionState.SignedOut, AdminSessionReason.SignedOut);

    public async Task ExpireAsync(AdminSessionReason reason = AdminSessionReason.RefreshRejected)
    {
        await ExpireIfCurrentAsync(Revision, AccessToken, RefreshToken, reason);
    }

    public async Task<bool> ExpireIfCurrentAsync(long expectedRevision, string? expectedAccessToken,
        string? expectedRefreshToken, AdminSessionReason reason)
    {
        if (!Matches(expectedRevision, expectedAccessToken, expectedRefreshToken)) return false;

        await StorageMutationGate.WaitAsync();
        try
        {
            if (!Matches(expectedRevision, expectedAccessToken, expectedRefreshToken)) return false;
            if (_storage is not null)
            {
                try
                {
                    var saved = await _storage.ReadAsync();
                    if (saved?.AuthenticationPending == true)
                    {
                        _logger.LogInformation(
                            "Admin session expiry deferred reason=AuthenticationInProgress revision={Revision}",
                            expectedRevision);
                        return false;
                    }
                    if (!string.IsNullOrWhiteSpace(saved?.AccessToken)
                        && !string.IsNullOrWhiteSpace(saved.RefreshToken)
                        && !string.Equals(saved.RefreshToken, expectedRefreshToken, StringComparison.Ordinal))
                    {
                        SetToken(saved.AccessToken, saved.RefreshToken, AdminSessionReason.AdoptedNewerSession);
                        return false;
                    }
                }
                catch (Exception ex) when (IsStorageException(ex))
                {
                    // Expire only this circuit. Never delete a snapshot that could belong
                    // to a newer circuit when the comparison read was unavailable.
                    Clear(AdminSessionState.Expired, reason);
                    return true;
                }
            }

            Clear(AdminSessionState.Expired, reason);
            if (_storage is not null)
            {
                try { await _storage.DeleteAsync(); }
                catch (Exception ex) when (IsStorageException(ex)) { }
            }
            return true;
        }
        finally { StorageMutationGate.Release(); }
    }

    public Task ClearAsync() => SignOutAsync();

    private async Task ClearStoredSnapshotAsync(AdminSessionState target, AdminSessionReason reason)
    {
        var refreshTokenToClear = RefreshToken;
        Clear(target, reason);
        var revision = Revision;
        await DeleteStoredSnapshotIfCurrentAsync(revision, refreshTokenToClear);
    }

    private async Task DeleteStoredSnapshotIfCurrentAsync(long expectedRevision, string? expectedRefreshToken)
    {
        if (_storage is null) return;
        await StorageMutationGate.WaitAsync();
        try
        {
            if (Revision != expectedRevision) return;
            try
            {
                var saved = await _storage.ReadAsync();
                if (saved is null || saved.AuthenticationPending
                    || !string.Equals(saved.RefreshToken, expectedRefreshToken, StringComparison.Ordinal))
                {
                    _logger.LogInformation(
                        "Admin session storage delete discarded reason=SnapshotChanged revision={Revision}",
                        expectedRevision);
                    return;
                }
                await _storage.DeleteAsync();
            }
            catch (Exception ex) when (IsStorageException(ex)) { }
        }
        finally { StorageMutationGate.Release(); }
    }

    private bool Matches(long revision, string? accessToken, string? refreshToken) =>
        Revision == revision
        && string.Equals(AccessToken, accessToken, StringComparison.Ordinal)
        && string.Equals(RefreshToken, refreshToken, StringComparison.Ordinal);

    private void Clear(AdminSessionState target, AdminSessionReason reason)
    {
        AccessToken = null;
        RefreshToken = null;
        Transition(target, reason);
    }

    private void Transition(AdminSessionState state, AdminSessionReason reason)
    {
        var previous = State;
        State = state;
        var revision = Interlocked.Increment(ref _revision);
        _logger.LogInformation(
            "Admin session transition {PreviousState} -> {CurrentState} reason={Reason} revision={Revision} hasAccessToken={HasAccessToken} hasRefreshToken={HasRefreshToken}",
            previous, state, reason, revision, !string.IsNullOrWhiteSpace(AccessToken), !string.IsNullOrWhiteSpace(RefreshToken));
        Changed?.Invoke();
    }

    private void LogDiscardedRestore(long startedRevision) =>
        _logger.LogInformation(
            "Admin session restore discarded reason=StaleRevision startedRevision={StartedRevision} currentRevision={CurrentRevision}",
            startedRevision, Revision);

    private static bool IsStorageException(Exception exception) => exception is
        JSException or InvalidOperationException or OperationCanceledException or CryptographicException or JsonException;
}
