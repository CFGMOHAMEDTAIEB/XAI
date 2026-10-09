using System.Net;
using System.Text;
using System.Text.Json;
using XaiCompress.Admin.Services;

if (args.Contains("--live-contract", StringComparer.Ordinal))
{
    await LiveAdminContract.RunAsync();
    return;
}

var paths = new List<string>();
var auth = new List<string?>();
var stats = """{"activeUsers":1,"totalUsers":1,"pendingVerification":0,"mfaEnabled":1,"authenticatorDevices":1,"compressionJobs":1,"successfulJobs":1,"failedJobs":0,"securityEvents":0,"jobsToday":1,"bytesSaved":20,"openIncidents":null,"quarantinedFiles":null,"losslessSuccessRate":100}""";
var users = """[{"id":2,"email":"managed@example.com","displayName":"Managed","role":"user","status":"ACTIVE","emailVerified":true,"phoneVerified":false,"mfaEnabled":true,"createdAt":"2026-01-01T00:00:00Z","lastLogin":null}]""";
var user = """{"id":2,"email":"managed@example.com","displayName":"Managed","role":"user","status":"ACTIVE","emailVerified":true,"mfaEnabled":true,"createdAt":"2026-01-01T00:00:00Z","lastLogin":null,"fileCount":1,"mfaEnrollmentState":"enabled"}""";
var jobs = """[{"id":"3","fileName":"sample.xaic","userEmail":"managed@example.com","mode":"hybrid","status":"completed","originalSize":100,"compressedSize":80,"integrityVerified":true,"createdAt":"2026-01-01T00:00:00Z"}]""";
var audit = """[{"id":4,"actor":"system","action":"admin.user_enabled","resource":"user:2","result":"success","ipAddress":"","createdAt":"2026-01-01T00:00:00Z"}]""";
var scanner = """{"status":"operational","clamav":"operational","yara":"operational","required":true}""";
var email = """{"provider":"mailpit","configured":true,"missing":[],"delivery_verified":false,"xaic_supported":true,"development_only":true,"api_key":"NOT_APPLICABLE","sender_configured":true,"smtp_security":"none"}""";
var devices = """[{"user_id":2,"device_id":"device-example","platform":"android","app_version":"1","status":"active","registered_at":"2026-01-01T00:00:00Z","last_activity":"2026-01-01T00:00:00Z"}]""";
var history = """[{"user_id":2,"type":"push_approved","result":"success","application":"XAICD","created_at":"2026-01-01T00:00:00Z"}]""";
var recovery = """[{"user_id":2,"issued":8,"used":1,"remaining":7}]""";
var shares = """[{"id":5,"sender_email":"managed@example.com","recipient_email":"recipient@example.com","file_name":"sample.xaic","created_at":null,"expires_at":"2027-01-01T00:00:00Z","status":"active","remaining_downloads":2}]""";
var bodies = new Dictionary<string, string> {
    ["/health"] = "{\"status\":\"ok\"}", ["/admin/stats"] = stats,
    ["/admin/users"] = users, ["/admin/users/2"] = user,
    ["/admin/jobs"] = jobs, ["/admin/audit"] = audit,
    ["/admin/security/scanner"] = scanner, ["/admin/email/configuration"] = email,
    ["/admin/authenticator/devices"] = devices,
    ["/admin/authenticator/history"] = history,
    ["/admin/authenticator/recovery"] = recovery,
    ["/admin/shares"] = shares
};
using var http = new HttpClient(new StubHandler(request => {
    var path = request.RequestUri!.AbsolutePath;
    paths.Add(request.Method + " " + path);
    auth.Add(request.Headers.Authorization?.Scheme);
    if (request.Method == HttpMethod.Get && bodies.TryGetValue(path, out var body)) return Json(HttpStatusCode.OK, body);
    if (request.Method == HttpMethod.Patch && path == "/admin/users/2") return Json(HttpStatusCode.OK, "{}");
    if (request.Method == HttpMethod.Post && path == "/admin/users") return Json(HttpStatusCode.Created, "{}");
    if (request.Method == HttpMethod.Post && path == "/admin/shares/5/revoke") return Json(HttpStatusCode.OK, "{}");
    if (request.Method == HttpMethod.Post && path == "/admin/authenticator/devices/device-example/revoke") return Json(HttpStatusCode.OK, "{}");
    if (request.Method == HttpMethod.Post && path.StartsWith("/admin/users/2/", StringComparison.Ordinal)) return Json(HttpStatusCode.OK, "{}");
    throw new Exception("Unexpected Admin request.");
})) { BaseAddress = new Uri("http://localhost:8000") };
var session = new AdminSession();
Check(session.State == AdminSessionState.SignedOut, "A new admin session was not signed out.");
var priorSnapshot = JsonSerializer.Deserialize<StoredAdminSession>(
    """{"AccessToken":"prior-access","RefreshToken":"prior-refresh"}""");
Check(priorSnapshot is not null && !priorSnapshot.AuthenticationPending
    && priorSnapshot.RefreshToken == "prior-refresh",
    "The new storage schema cannot read the previous session snapshot.");
session.BeginAuthentication();
Check(session.State == AdminSessionState.Authenticating, "Authentication state was not explicit.");
session.RequireMfa();
Check(session.State == AdminSessionState.MfaRequired, "MFA challenge state was not explicit.");
session.SetToken("test-access", "test-refresh");
Check(session.State == AdminSessionState.Authenticated, "A valid token did not establish an authenticated state.");

var delayedStore = new DelayedSessionStore(new StoredAdminSession("stale-access", "stale-refresh"));
var raceSession = new AdminSession(delayedStore);
var restore = raceSession.RestoreAsync();
await delayedStore.ReadStarted.Task;
raceSession.BeginAuthentication();
raceSession.SetToken("fresh-access", "fresh-refresh");
delayedStore.ReleaseRead.SetResult();
await restore;
Check(raceSession.AccessToken == "fresh-access" && raceSession.RefreshToken == "fresh-refresh",
    "A stale asynchronous restore overwrote a newly authenticated session.");

var missingStore = new DelayedSessionStore(null);
var missingRestoreSession = new AdminSession(missingStore);
var missingRestore = missingRestoreSession.RestoreAsync();
await missingStore.ReadStarted.Task;
await missingRestoreSession.SetTokenAsync("login-access", "login-refresh");
missingStore.ReleaseRead.SetResult();
await missingRestore;
Check(missingRestoreSession.State == AdminSessionState.Authenticated
    && missingRestoreSession.AccessToken == "login-access"
    && missingRestoreSession.RefreshToken == "login-refresh",
    "A delayed missing restore result replaced a successful login.");
Check(missingStore.Deletes == 0 && missingStore.Value?.RefreshToken == "login-refresh",
    "A delayed missing restore result cleared the newly stored login.");

var failingStore = new DelayedSessionStore(null, failRead: true);
var failingRestoreSession = new AdminSession(failingStore);
var failingRestore = failingRestoreSession.RestoreAsync();
await failingStore.ReadStarted.Task;
await failingRestoreSession.SetTokenAsync("fresh-after-error", "fresh-refresh-after-error");
failingStore.ReleaseRead.SetResult();
await failingRestore;
Check(failingRestoreSession.State == AdminSessionState.Authenticated
    && failingRestoreSession.RefreshToken == "fresh-refresh-after-error"
    && failingStore.Deletes == 0,
    "A delayed restore exception cleared a successful login.");

var immediateRequestCount = 0;
using var immediateHttp = new HttpClient(new StubHandler(request => {
    immediateRequestCount++;
    if (request.RequestUri!.AbsolutePath == "/auth/login")
        return Json(HttpStatusCode.OK, """{"access_token":"login-access-immediate","refresh_token":"login-refresh-immediate"}""");
    if (request.RequestUri.AbsolutePath == "/admin/stats")
    {
        Check(request.Headers.Authorization?.Parameter == "login-access-immediate",
            "Admin validation did not receive the freshly issued access token.");
        return Json(HttpStatusCode.OK, stats);
    }
    if (request.RequestUri.AbsolutePath == "/admin/users")
    {
        Check(request.Headers.Authorization?.Parameter == "login-access-immediate",
            "The first protected request did not receive the freshly issued access token.");
        return Json(HttpStatusCode.OK, users);
    }
    throw new Exception("Unexpected immediate-login request.");
})) { BaseAddress = new Uri("http://localhost:8000") };
var immediateSession = new AdminSession();
var immediateClient = new PlatformApiClient(immediateHttp, immediateSession);
await immediateClient.LoginAsync("admin@example.com", "password", "123456");
Check(immediateSession.State == AdminSessionState.Authenticated
    && immediateSession.RefreshToken == "login-refresh-immediate",
    "Successful login did not make both tokens available before navigation.");
Check((await immediateClient.GetUsersAsync()).Count == 1 && immediateRequestCount == 3,
    "The immediate protected request failed after successful login.");

var client = new PlatformApiClient(http, session);
Check((await client.GetUsersAsync())[0].EmailVerified, "User verification did not deserialize.");
Check((await client.GetUserAsync(2)).Status == "ACTIVE", "User detail status did not deserialize.");
Check((await client.GetJobsAsync())[0].OriginalSize == 100, "Job size did not deserialize.");
Check((await client.GetAuditAsync())[0].Action == "admin.user_enabled", "Audit action did not deserialize.");
Check((await client.GetDashboardAsync()).TotalUsers == 1, "Stats did not deserialize.");
Check((await client.GetScannerAsync()).Yara == "operational", "Scanner did not deserialize.");
Check((await client.GetEmailConfigurationAsync()).DevelopmentOnly, "Email configuration did not deserialize.");
Check((await client.GetAuthenticatorDevicesAsync())[0].UserId == 2, "Device snake-case fields did not deserialize.");
Check((await client.GetAuthenticatorHistoryAsync())[0].UserId == 2, "History snake-case fields did not deserialize.");
Check((await client.GetRecoveryCodeSummariesAsync())[0].Remaining == 7, "Recovery summary did not deserialize.");
Check((await client.GetSharesAsync())[0].RemainingDownloads == 2, "Share metadata did not deserialize.");
Check((await client.GetHealthAsync()).Count == 5, "Readiness prerequisites did not finish.");
await client.CreateUserAsync("invited@example.com", "Invited Person", "user");
await client.UpdateUserAsync(2, "admin", null);
await client.RevokeRefreshSessionsAsync(2);
await client.ResetUserMfaAsync(2);
await client.RevokeAuthenticatorDeviceAsync("device-example");
await client.RevokeShareAsync(5);
Check(paths.Count == auth.Count && paths.Zip(auth).All(x => x.First == "GET /health" || x.Second == "Bearer"),
    "A protected request omitted the bearer header.");

using var deniedHttp = new HttpClient(new StubHandler(_ => Json(HttpStatusCode.Forbidden, "{}")))
    { BaseAddress = new Uri("http://localhost:8000") };
var deniedSession = new AdminSession(); deniedSession.SetToken("test-access");
try { await new PlatformApiClient(deniedHttp, deniedSession).GetUsersAsync(); throw new Exception("403 was not rejected."); }
catch (AdminApiAuthorizationException ex) when (ex.StatusCode == HttpStatusCode.Forbidden)
{ Check(deniedSession.IsAuthenticated, "403 incorrectly cleared the session."); }

var first = true;
using var refreshHttp = new HttpClient(new StubHandler(request => {
    if (request.RequestUri!.AbsolutePath == "/auth/refresh")
        return Json(HttpStatusCode.OK, "{\"access_token\":\"renewed\",\"refresh_token\":\"rotated\"}");
    if (first) { first = false; return Json(HttpStatusCode.Unauthorized, "{}"); }
    Check(request.Headers.Authorization?.Parameter == "renewed", "GET did not retry with renewed access.");
    return Json(HttpStatusCode.OK, users);
})) { BaseAddress = new Uri("http://localhost:8000") };
var refreshSession = new AdminSession(); refreshSession.SetToken("expired", "refresh");
Check((await new PlatformApiClient(refreshHttp, refreshSession).GetUsersAsync()).Count == 1,
    "Expired Admin GET was not retried.");
Check(refreshSession.AccessToken == "renewed", "Renewed session was not stored.");
var accessOnlyFirst = true;
using var accessOnlyRefreshHttp = new HttpClient(new StubHandler(request => {
    if (request.RequestUri!.AbsolutePath == "/auth/refresh")
        return Json(HttpStatusCode.OK, "{\"access_token\":\"renewed-without-rotation\"}");
    if (accessOnlyFirst) { accessOnlyFirst = false; return Json(HttpStatusCode.Unauthorized, "{}"); }
    return Json(HttpStatusCode.OK, users);
})) { BaseAddress = new Uri("http://localhost:8000") };
var accessOnlySession = new AdminSession(); accessOnlySession.SetToken("expired", "still-valid-refresh");
await new PlatformApiClient(accessOnlyRefreshHttp, accessOnlySession).GetUsersAsync();
Check(accessOnlySession.RefreshToken == "still-valid-refresh",
    "A refresh response without rotation discarded the current refresh token.");
var refreshCount = 0;
using var concurrentHttp = new HttpClient(new StubHandler(request => {
    if (request.RequestUri!.AbsolutePath == "/auth/refresh")
    {
        Interlocked.Increment(ref refreshCount);
        return Json(HttpStatusCode.OK, "{\"access_token\":\"renewed\",\"refresh_token\":\"rotated\"}");
    }
    return request.Headers.Authorization?.Parameter == "expired"
        ? Json(HttpStatusCode.Unauthorized, "{}") : Json(HttpStatusCode.OK, users);
})) { BaseAddress = new Uri("http://localhost:8000") };
var concurrentSession = new AdminSession(); concurrentSession.SetToken("expired", "refresh");
var concurrentClient = new PlatformApiClient(concurrentHttp, concurrentSession);
await Task.WhenAll(Enumerable.Range(0, 5).Select(_ => concurrentClient.GetUsersAsync()));
Check(refreshCount == 1, "Concurrent 401 responses caused multiple refresh requests.");

var mutationRefreshCount = 0;
using var mutationHttp = new HttpClient(new StubHandler(request => {
    if (request.RequestUri!.AbsolutePath == "/auth/refresh")
    {
        mutationRefreshCount++;
        return Json(HttpStatusCode.OK, "{\"access_token\":\"renewed\",\"refresh_token\":\"rotated\"}");
    }
    return request.Headers.Authorization?.Parameter == "expired"
        ? Json(HttpStatusCode.Unauthorized, "{}") : Json(HttpStatusCode.OK, "{}");
})) { BaseAddress = new Uri("http://localhost:8000") };
var mutationSession = new AdminSession(); mutationSession.SetToken("expired", "refresh");
await new PlatformApiClient(mutationHttp, mutationSession).RevokeShareAsync(5);
Check(mutationRefreshCount == 1, "Mutation did not retry once after refresh.");
using var invalidHttp = new HttpClient(new StubHandler(request =>
    Json(HttpStatusCode.Unauthorized, "{}"))) { BaseAddress = new Uri("http://localhost:8000") };
var invalidSession = new AdminSession(); invalidSession.SetToken("expired", "revoked");
try { await new PlatformApiClient(invalidHttp, invalidSession).GetUsersAsync(); throw new Exception("Invalid refresh was accepted."); }
catch (AdminApiAuthorizationException ex) when (ex.StatusCode == HttpStatusCode.Unauthorized)
{ Check(!invalidSession.IsAuthenticated && invalidSession.State == AdminSessionState.Expired, "Rejected refresh did not expire the session."); }

using var unavailableRefreshHttp = new HttpClient(new StubHandler(request => {
    if (request.RequestUri!.AbsolutePath == "/auth/refresh") throw new HttpRequestException("Temporary outage");
    return Json(HttpStatusCode.Unauthorized, "{}");
})) { BaseAddress = new Uri("http://localhost:8000") };
var unavailableRefreshSession = new AdminSession(); unavailableRefreshSession.SetToken("expired", "still-valid");
try { await new PlatformApiClient(unavailableRefreshHttp, unavailableRefreshSession).GetUsersAsync(); throw new Exception("Refresh outage was hidden."); }
catch (HttpRequestException)
{ Check(unavailableRefreshSession.State == AdminSessionState.Authenticated, "A network outage incorrectly expired the session."); }

using var malformedRefreshHttp = new HttpClient(new StubHandler(request =>
    request.RequestUri!.AbsolutePath == "/auth/refresh"
        ? Json(HttpStatusCode.OK, "{}") : Json(HttpStatusCode.Unauthorized, "{}")))
    { BaseAddress = new Uri("http://localhost:8000") };
var malformedRefreshSession = new AdminSession();
malformedRefreshSession.SetToken("expired", "still-valid");
try { await new PlatformApiClient(malformedRefreshHttp, malformedRefreshSession).GetUsersAsync(); throw new Exception("Incomplete refresh was accepted."); }
catch (InvalidOperationException)
{ Check(malformedRefreshSession.State == AdminSessionState.Authenticated, "An incomplete refresh response incorrectly expired the session."); }

var sharedStore = new MemorySessionStore(new StoredAdminSession("new-circuit-access", "rotated-by-new-circuit"));
var oldCircuitSession = new AdminSession(sharedStore); oldCircuitSession.SetToken("old-circuit-access", "consumed-refresh");
var oldCircuitRefreshCalls = 0;
using var oldCircuitHttp = new HttpClient(new StubHandler(request => {
    if (request.RequestUri!.AbsolutePath == "/auth/refresh") { oldCircuitRefreshCalls++; return Json(HttpStatusCode.Unauthorized, "{}"); }
    return request.Headers.Authorization?.Parameter == "old-circuit-access"
        ? Json(HttpStatusCode.Unauthorized, "{}") : Json(HttpStatusCode.OK, users);
})) { BaseAddress = new Uri("http://localhost:8000") };
Check((await new PlatformApiClient(oldCircuitHttp, oldCircuitSession).GetUsersAsync()).Count == 1,
    "An older circuit did not adopt the rotated browser session.");
Check(oldCircuitRefreshCalls == 0 && oldCircuitSession.State == AdminSessionState.Authenticated,
    "An older circuit retried a consumed refresh token instead of adopting the newer session.");

var guardedStore = new MemorySessionStore(new StoredAdminSession("new-login-access", "new-login-refresh"));
var guardedOldSession = new AdminSession(guardedStore);
guardedOldSession.SetToken("old-access", "old-refresh");
var expired = await guardedOldSession.ExpireIfCurrentAsync(guardedOldSession.Revision,
    "old-access", "old-refresh", AdminSessionReason.RefreshRejected);
Check(!expired && guardedOldSession.State == AdminSessionState.Authenticated
    && guardedOldSession.RefreshToken == "new-login-refresh" && guardedStore.Deletes == 0,
    "An old circuit expiry deleted or replaced a newer stored login.");

var staleSignOutStore = new MemorySessionStore(new StoredAdminSession("new-login-access", "new-login-refresh"));
var staleSignOutCircuit = new AdminSession(staleSignOutStore);
staleSignOutCircuit.SetToken("old-access", "old-refresh");
await staleSignOutCircuit.SignOutAsync();
Check(staleSignOutCircuit.State == AdminSessionState.SignedOut
    && (await staleSignOutStore.ReadAsync())?.RefreshToken == "new-login-refresh"
    && staleSignOutStore.Deletes == 0,
    "An older circuit sign-out deleted a newer stored login.");

var pendingStore = new MemorySessionStore(new StoredAdminSession("old-access", "old-refresh"));
var pendingOldCircuit = new AdminSession(pendingStore);
pendingOldCircuit.SetToken("old-access", "old-refresh");
var pendingLoginCircuit = new AdminSession(pendingStore);
await pendingLoginCircuit.BeginAuthenticationAsync();
Check((await pendingStore.ReadAsync())?.AuthenticationPending == true,
    "Starting login did not mark authentication in progress in protected storage.");
var pendingExpired = await pendingOldCircuit.ExpireIfCurrentAsync(pendingOldCircuit.Revision,
    "old-access", "old-refresh", AdminSessionReason.RefreshRejected);
Check(!pendingExpired && pendingOldCircuit.State == AdminSessionState.Authenticated
    && pendingStore.Deletes == 0,
    "An older circuit expired or deleted a login that was waiting for MFA.");
await pendingLoginCircuit.SetTokenAsync("new-access", "new-refresh");
Check((await pendingStore.ReadAsync())?.RefreshToken == "new-refresh"
    && (await pendingStore.ReadAsync())?.AuthenticationPending == false,
    "Successful login did not replace the pending authentication marker.");

var coordinator = new AdminRefreshCoordinator();
var rotatingSession = new AdminSession();
rotatingSession.SetToken("rotation-old-access", "rotation-old-refresh");
using var rotatingHttp = new HttpClient(new StubHandler(request => {
    if (request.RequestUri!.AbsolutePath == "/auth/refresh")
        return Json(HttpStatusCode.OK, """{"access_token":"rotation-new-access","refresh_token":"rotation-new-refresh"}""");
    return request.Headers.Authorization?.Parameter == "rotation-old-access"
        ? Json(HttpStatusCode.Unauthorized, "{}") : Json(HttpStatusCode.OK, users);
})) { BaseAddress = new Uri("http://localhost:8000") };
await new PlatformApiClient(rotatingHttp, rotatingSession, coordinator).GetUsersAsync();

var staleRefreshCalls = 0;
var staleCircuit = new AdminSession();
staleCircuit.SetToken("rotation-old-access", "rotation-old-refresh");
using var staleHttp = new HttpClient(new StubHandler(request => {
    if (request.RequestUri!.AbsolutePath == "/auth/refresh")
    {
        staleRefreshCalls++;
        return Json(HttpStatusCode.Unauthorized, "{}");
    }
    return request.Headers.Authorization?.Parameter == "rotation-old-access"
        ? Json(HttpStatusCode.Unauthorized, "{}") : Json(HttpStatusCode.OK, users);
})) { BaseAddress = new Uri("http://localhost:8000") };
Check((await new PlatformApiClient(staleHttp, staleCircuit, coordinator).GetUsersAsync()).Count == 1,
    "A stale circuit could not adopt the process refresh handoff.");
Check(staleRefreshCalls == 0 && staleCircuit.State == AdminSessionState.Authenticated
    && staleCircuit.RefreshToken == "rotation-new-refresh",
    "A stale circuit retried a consumed refresh token after another circuit rotated it.");

var loginPage = File.ReadAllText(Path.Combine(Directory.GetCurrentDirectory(),
    "apps", "admin_dotnet", "Components", "Pages", "Login.razor"));
Check(loginPage.Contains("NavigateTo(\"/dashboard\", replace: true)", StringComparison.Ordinal),
    "Successful login does not replace the expired query URL with /dashboard.");
await DashboardPartialTest.RunAsync();
await AdminReadStateTest.RunAsync();
await AuthenticatorPartialTest.RunAsync();
foreach (var page in new[] { "Users", "Jobs", "Shares", "Audit", "Authenticator", "Scanner", "SystemHealth", "Email", "UserDetails" })
{
    var source = File.ReadAllText(Path.Combine(Directory.GetCurrentDirectory(),
        "apps", "admin_dotnet", "Components", "Pages", page + ".razor"));
    Check(source.Contains("Error=\"@Error\"", StringComparison.Ordinal) &&
        !source.Contains("Error=\"Error\"", StringComparison.Ordinal),
        $"{page} passes a literal error string instead of its load state.");
}
Console.WriteLine("Admin data/session/client contract: focused checks passed.");

static HttpResponseMessage Json(HttpStatusCode status, string body) => new(status)
    { Content = new StringContent(body, Encoding.UTF8, "application/json") };
static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
sealed class StubHandler(Func<HttpRequestMessage, HttpResponseMessage> send) : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        => Task.FromResult(send(request));
}
sealed class DelayedSessionStore : IAdminSessionStore
{
    private readonly StoredAdminSession? _readValue;
    private readonly bool _failRead;
    public DelayedSessionStore(StoredAdminSession? value, bool failRead = false)
    {
        _readValue = value;
        _failRead = failRead;
        Value = value;
    }
    public StoredAdminSession? Value { get; private set; }
    public int Deletes { get; private set; }
    public TaskCompletionSource ReadStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public TaskCompletionSource ReleaseRead { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public async Task<StoredAdminSession?> ReadAsync()
    {
        ReadStarted.SetResult();
        await ReleaseRead.Task;
        if (_failRead) throw new InvalidOperationException("Simulated unreadable snapshot");
        return _readValue;
    }
    public Task WriteAsync(StoredAdminSession session) { Value = session; return Task.CompletedTask; }
    public Task DeleteAsync() { Deletes++; Value = null; return Task.CompletedTask; }
}
sealed class MemorySessionStore(StoredAdminSession? value) : IAdminSessionStore
{
    public int Deletes { get; private set; }
    public Task<StoredAdminSession?> ReadAsync() => Task.FromResult(value);
    public Task WriteAsync(StoredAdminSession session) { value = session; return Task.CompletedTask; }
    public Task DeleteAsync() { Deletes++; value = null; return Task.CompletedTask; }
}
