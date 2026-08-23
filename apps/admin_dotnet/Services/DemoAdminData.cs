using XaiCompress.Admin.Models;

namespace XaiCompress.Admin.Services;

public sealed class DemoAdminData
{
    private static readonly DateTimeOffset Now = DateTimeOffset.UtcNow;

    public DashboardStats Dashboard { get; } = new(
        ActiveUsers: 128,
        JobsToday: 342,
        BytesSaved: 8_623_489_024,
        OpenIncidents: 4,
        QuarantinedFiles: 7,
        LosslessSuccessRate: 100.0);

    public IReadOnlyList<UserSummary> Users { get; } = new List<UserSummary>
    {
        new(1, "admin@xai.local", "Platform Administrator", "SUPER_ADMIN", "Active", true, Now.AddMonths(-6), Now.AddMinutes(-12)),
        new(2, "analyst@xai.local", "Security Analyst", "SECURITY_ANALYST", "Active", true, Now.AddMonths(-3), Now.AddHours(-1)),
        new(3, "user@example.com", "Demo User", "USER", "Active", true, Now.AddDays(-12), Now.AddDays(-1)),
        new(4, "suspended@example.com", "Suspended User", "USER", "Suspended", false, Now.AddMonths(-1), Now.AddDays(-8)),
    };

    public IReadOnlyList<CompressionJob> Jobs { get; } = new List<CompressionJob>
    {
        new("JOB-24081", "vehicle_trace.csv", "user@example.com", "Neural", "Completed", 6_400_000, 2_910_000, true, Now.AddMinutes(-8)),
        new("JOB-24080", "archive.zip", "user@example.com", "Raw fallback", "Completed", 2_400_000, 2_400_512, true, Now.AddMinutes(-20)),
        new("JOB-24079", "diagnostic.log", "analyst@xai.local", "Static", "Completed", 980_000, 341_200, true, Now.AddHours(-1)),
        new("JOB-24078", "telemetry.bin", "user@example.com", "Neural", "Processing", 80_000_000, 0, false, Now.AddMinutes(-3)),
    };

    public IReadOnlyList<SecurityIncident> Incidents { get; } = new List<SecurityIncident>
    {
        new("INC-1007", "High", "YARA match", "firmware_sample.bin", "Open", "A custom suspicious-pattern rule matched the uploaded file.", Now.AddMinutes(-18)),
        new("INC-1006", "Medium", "Repeated code attempts", "Share XC-REDACTED", "Investigating", "The share-code rate limit was triggered.", Now.AddHours(-2)),
        new("INC-1005", "Low", "MIME mismatch", "document.pdf.exe", "Resolved", "The declared extension did not match the detected file type.", Now.AddDays(-1)),
    };

    public IReadOnlyList<QuarantinedFile> Quarantine { get; } = new List<QuarantinedFile>
    {
        new("Q-501", "firmware_sample.bin", "user@example.com", "Clean", new[] { "Suspicious_Firmware_Pattern" }, new string('a', 64), Now.AddMinutes(-18)),
        new("Q-500", "document.pdf.exe", "suspended@example.com", "Win.Test.EICAR_HDB-1", Array.Empty<string>(), new string('b', 64), Now.AddDays(-1)),
    };

    public IReadOnlyList<AuditEvent> Audit { get; } = new List<AuditEvent>
    {
        new(9008, "admin@xai.local", "incident.reviewed", "INC-1007", "success", "10.0.0.11", Now.AddMinutes(-3)),
        new(9007, "user@example.com", "compression.completed", "JOB-24081", "success", "10.0.0.44", Now.AddMinutes(-8)),
        new(9006, "security-scanner", "file.quarantined", "Q-501", "success", "internal", Now.AddMinutes(-18)),
        new(9005, "unknown", "share.redeem", "share-redacted", "denied", "10.0.0.92", Now.AddHours(-2)),
    };

    public IReadOnlyList<ServiceHealth> Health { get; } = new List<ServiceHealth>
    {
        new("FastAPI", "Unknown", 0, "0.2.0", Now),
        new("PostgreSQL", "Healthy", 4.2, "17", Now),
        new("Redis", "Healthy", 1.1, "7", Now),
        new("MinIO", "Healthy", 8.8, "latest", Now),
        new("Keycloak", "Healthy", 18.4, "26", Now),
        new("ClamAV", "Healthy", 12.0, "stable", Now),
        new("Compression Engine", "Healthy", 32.5, "0.1.0", Now),
    };
}
