using System.Net.Http.Headers;
using System.Net.Http.Json;
using XaiCompress.Admin.Models;

namespace XaiCompress.Admin.Services;

public sealed class PlatformApiClient
{
    private readonly HttpClient _http;
    private readonly AdminSession _session;
    private readonly DemoAdminData _demo;
    private readonly IConfiguration _configuration;

    public PlatformApiClient(
        HttpClient http,
        AdminSession session,
        DemoAdminData demo,
        IConfiguration configuration)
    {
        _http = http;
        _session = session;
        _demo = demo;
        _configuration = configuration;
    }

    private bool DemoFallback => _configuration.GetValue("PlatformApi:UseDemoFallback", true);

    private void Authorize()
    {
        _http.DefaultRequestHeaders.Authorization = string.IsNullOrWhiteSpace(_session.AccessToken)
            ? null
            : new AuthenticationHeaderValue("Bearer", _session.AccessToken);
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

    public Task<DashboardStats> GetDashboardAsync() => Task.FromResult(_demo.Dashboard);
    public Task<IReadOnlyList<UserSummary>> GetUsersAsync() => Task.FromResult(_demo.Users);
    public Task<IReadOnlyList<CompressionJob>> GetJobsAsync() => Task.FromResult(_demo.Jobs);
    public Task<IReadOnlyList<SecurityIncident>> GetIncidentsAsync() => Task.FromResult(_demo.Incidents);
    public Task<IReadOnlyList<QuarantinedFile>> GetQuarantineAsync() => Task.FromResult(_demo.Quarantine);
    public Task<IReadOnlyList<AuditEvent>> GetAuditAsync() => Task.FromResult(_demo.Audit);

    public async Task<IReadOnlyList<ServiceHealth>> GetHealthAsync()
    {
        var apiHealthy = await IsHealthyAsync();
        return _demo.Health
            .Select(service => service.Name == "FastAPI"
                ? service with { Status = apiHealthy ? "Healthy" : "Unavailable", CheckedAt = DateTimeOffset.UtcNow }
                : service)
            .ToList();
    }
}
