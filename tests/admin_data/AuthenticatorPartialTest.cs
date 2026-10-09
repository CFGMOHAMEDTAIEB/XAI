using System.Net;
using System.Reflection;
using System.Text;
using Microsoft.Extensions.Logging.Abstractions;
using XaiCompress.Admin.Components.Pages;
using XaiCompress.Admin.Models;
using XaiCompress.Admin.Services;

internal static class AuthenticatorPartialTest
{
    public static async Task RunAsync()
    {
        using var http = new HttpClient(new Handler(request => request.RequestUri!.AbsolutePath switch
        {
            "/admin/authenticator/devices" => Json(HttpStatusCode.OK, "[]"),
            "/admin/authenticator/history" => Json(HttpStatusCode.InternalServerError, "{}"),
            _ => throw new InvalidOperationException("Unexpected authenticator endpoint")
        })) { BaseAddress = new Uri("http://localhost:8000") };
        var session = new AdminSession();
        session.SetToken("authenticator-test-access", "authenticator-test-refresh");
        var page = new Authenticator();
        var baseType = typeof(AdminReadPage<IReadOnlyList<AuthenticatorDevice>>);
        var flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        baseType.GetProperty("Api", flags)!.SetValue(page, new PlatformApiClient(http, session));
        baseType.GetProperty("Session", flags)!.SetValue(page, session);
        baseType.GetProperty("Logger", flags)!.SetValue(page,
            NullLogger<AdminReadPage<IReadOnlyList<AuthenticatorDevice>>>.Instance);
        await (Task)typeof(Authenticator).GetMethod("LoadAllAsync", flags)!.Invoke(page, null)!;
        if (baseType.GetField("Data", flags)!.GetValue(page) is not IReadOnlyList<AuthenticatorDevice> devices ||
            devices.Count != 0 || baseType.GetField("Error", flags)!.GetValue(page) is not null ||
            typeof(Authenticator).GetField("_historyError", flags)!.GetValue(page) is null)
            throw new InvalidOperationException("A history-only failure hid a successful empty device list.");
    }

    private static HttpResponseMessage Json(HttpStatusCode status, string body) => new(status)
        { Content = new StringContent(body, Encoding.UTF8, "application/json") };
    private sealed class Handler(Func<HttpRequestMessage, HttpResponseMessage> send) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            Task.FromResult(send(request));
    }
}
