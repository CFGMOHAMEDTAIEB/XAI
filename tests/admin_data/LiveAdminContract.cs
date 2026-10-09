using System.Text.Json;
using XaiCompress.Admin.Models;

internal static class LiveAdminContract
{
    public static async Task RunAsync()
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
        var checkedPaths = new HashSet<string>(StringComparer.Ordinal);
        while (await Console.In.ReadLineAsync() is { } line)
        {
            using var entry = JsonDocument.Parse(line.TrimStart('\uFEFF'));
            var path = entry.RootElement.GetProperty("path").GetString()
                ?? throw new InvalidOperationException("Missing endpoint path.");
            var body = entry.RootElement.GetProperty("body").GetRawText();
            object? parsed = path switch
            {
                "/admin/stats" => JsonSerializer.Deserialize<DashboardStats>(body, options),
                "/admin/users" => JsonSerializer.Deserialize<List<UserSummary>>(body, options),
                "/admin/jobs" => JsonSerializer.Deserialize<List<CompressionJob>>(body, options),
                "/admin/shares" => JsonSerializer.Deserialize<List<AdminShare>>(body, options),
                "/admin/audit" => JsonSerializer.Deserialize<List<AuditEvent>>(body, options),
                "/admin/authenticator/devices" => JsonSerializer.Deserialize<List<AuthenticatorDevice>>(body, options),
                "/admin/authenticator/history" => JsonSerializer.Deserialize<List<AuthenticatorHistory>>(body, options),
                "/admin/security/scanner" => JsonSerializer.Deserialize<ScannerStatus>(body, options),
                "/admin/email/configuration" => JsonSerializer.Deserialize<EmailConfiguration>(body, options),
                _ => throw new InvalidOperationException("Unexpected endpoint path.")
            };
            if (parsed is null) throw new InvalidOperationException($"Null response for {path}.");
            checkedPaths.Add(path);
        }
        if (checkedPaths.Count != 9)
            throw new InvalidOperationException($"Expected 9 Admin response shapes, received {checkedPaths.Count}.");
        Console.WriteLine("Live Admin response DTO contract: 9 endpoints passed.");
    }
}
