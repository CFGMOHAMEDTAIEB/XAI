using System.Net;
using System.Text;
using System.Text.Json;
using XaiCompress.Admin.Services;

var resetAuthorization = new string('t', 48);
var calls = new List<string>();
using var http = new HttpClient(new StubHandler(async request =>
{
    Check(request.Method == HttpMethod.Post, "Recovery must use POST.");
    Check(request.Headers.Authorization is null, "Recovery must not require or send an admin session.");
    var path = request.RequestUri?.AbsolutePath ?? "";
    calls.Add(path);
    using var body = JsonDocument.Parse(await request.Content!.ReadAsStringAsync());
    return path switch
    {
        "/auth/password/forgot" => Forgot(body),
        "/auth/password/verify-code" => Verify(body),
        "/auth/password/reset" => Reset(body),
        _ => throw new Exception("Unexpected recovery endpoint.")
    };
})) { BaseAddress = new Uri("http://localhost:8000") };
var client = new PlatformApiClient(http, new AdminSession());

await client.RequestPasswordResetAsync("pfe-admin@example.com");
var authorization = await client.VerifyPasswordResetCodeAsync("pfe-admin@example.com", "123456");
Check(authorization == resetAuthorization, "Verification authorization was not returned.");
await client.ResetPasswordAsync(authorization, "example-new-password");
Check(calls.SequenceEqual(["/auth/password/forgot", "/auth/password/verify-code", "/auth/password/reset"]),
    "Recovery call order is wrong.");
await ExpectInvalid(() => client.VerifyPasswordResetCodeAsync("pfe-admin@example.com", "000000"));
await ExpectInvalid(() => client.ResetPasswordAsync("expired", "example-new-password"));
Console.WriteLine("Admin password recovery client contract: 5 focused checks passed.");

static HttpResponseMessage Forgot(JsonDocument body)
{
    Check(body.RootElement.GetProperty("identifier").GetString() == "pfe-admin@example.com", "Forgot identifier mismatch.");
    return Json(HttpStatusCode.OK, "{\"accepted\":true}");
}

static HttpResponseMessage Verify(JsonDocument body)
{
    Check(body.RootElement.GetProperty("identifier").GetString() == "pfe-admin@example.com", "Verify identifier mismatch.");
    var valid = body.RootElement.GetProperty("code").GetString() == "123456";
    return valid ? Json(HttpStatusCode.OK, "{\"reset_token\":\"" + new string('t', 48) + "\"}")
        : Json(HttpStatusCode.BadRequest, "{}");
}

static HttpResponseMessage Reset(JsonDocument body)
{
    Check(body.RootElement.GetProperty("new_password").GetString() == "example-new-password", "New password field mismatch.");
    var valid = body.RootElement.GetProperty("reset_token").GetString() == new string('t', 48);
    return Json(valid ? HttpStatusCode.OK : HttpStatusCode.BadRequest, "{}");
}

static HttpResponseMessage Json(HttpStatusCode status, string content) => new(status)
{
    Content = new StringContent(content, Encoding.UTF8, "application/json")
};

static async Task ExpectInvalid(Func<Task> action)
{
    try { await action(); }
    catch (AdminRecoveryInvalidException) { return; }
    throw new Exception("Invalid recovery input was not rejected.");
}

static void Check(bool condition, string message)
{
    if (!condition) throw new Exception(message);
}

sealed class StubHandler(Func<HttpRequestMessage, Task<HttpResponseMessage>> send) : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => send(request);
}
