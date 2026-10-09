using System.Net;
using System.Reflection;
using System.Text;
using Microsoft.Extensions.Logging.Abstractions;
using XaiCompress.Admin.Components.Pages;
using XaiCompress.Admin.Services;

internal static class DashboardPartialTest
{
    public static async Task RunAsync()
    {
        await VerifyAsync(failStats: false, failJobs: true);
        await VerifyAsync(failStats: true, failJobs: false);
    }

    private static async Task VerifyAsync(bool failStats, bool failJobs)
    {
        var stats = """{"activeUsers":1,"totalUsers":1,"pendingVerification":0,"mfaEnabled":1,"authenticatorDevices":0,"compressionJobs":0,"successfulJobs":0,"failedJobs":0,"securityEvents":0,"jobsToday":0,"bytesSaved":0,"openIncidents":null,"quarantinedFiles":null,"losslessSuccessRate":null}""";
        using var http = new HttpClient(new Handler(request => request.RequestUri!.AbsolutePath switch
        {
            "/admin/stats" => failStats ? Json(HttpStatusCode.InternalServerError, "{}") : Json(HttpStatusCode.OK, stats),
            "/admin/jobs" => failJobs ? Json(HttpStatusCode.InternalServerError, "{}") : Json(HttpStatusCode.OK, "[]"),
            "/admin/shares" or "/admin/audit" => Json(HttpStatusCode.OK, "[]"),
            "/admin/security/scanner" => Json(HttpStatusCode.OK, """{"status":"operational","clamav":"operational","yara":"operational","required":true}"""),
            "/admin/email/configuration" => Json(HttpStatusCode.OK, """{"provider":"mailpit","configured":true,"missing":[],"delivery_verified":false,"xaic_supported":true,"development_only":true,"api_key":"NOT_APPLICABLE","sender_configured":true,"smtp_security":"none"}"""),
            _ => throw new InvalidOperationException("Unexpected dashboard endpoint")
        })) { BaseAddress = new Uri("http://localhost:8000") };
        var session = new AdminSession();
        session.SetToken("dashboard-test-access", "dashboard-test-refresh");
        var page = new Home();
        Set(page, "Api", new PlatformApiClient(http, session));
        Set(page, "Session", session);
        Set(page, "Logger", NullLogger<Home>.Instance);
        await (Task)typeof(Home).GetMethod("LoadAsync", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(page, null)!;
        if ((Get(page, "_stats") is null) != failStats || Get(page, "_error") is not null ||
            (Get(page, "_statsError") is null) != !failStats || (Get(page, "_jobsError") is null) != !failJobs ||
            Get(page, "_sharesError") is not null || Get(page, "_auditError") is not null ||
            Get(page, "_scannerError") is not null || Get(page, "_emailError") is not null)
            throw new InvalidOperationException("A single failed dashboard widget hid successful dashboard data.");
    }

    private static void Set(Home page, string name, object value) =>
        typeof(Home).GetProperty(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(page, value);
    private static object? Get(Home page, string name) =>
        typeof(Home).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(page);
    private static HttpResponseMessage Json(HttpStatusCode status, string body) => new(status)
        { Content = new StringContent(body, Encoding.UTF8, "application/json") };
    private sealed class Handler(Func<HttpRequestMessage, HttpResponseMessage> send) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            Task.FromResult(send(request));
    }
}
