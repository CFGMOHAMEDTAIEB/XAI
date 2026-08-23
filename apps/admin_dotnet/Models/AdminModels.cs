namespace XaiCompress.Admin.Models;

public sealed record DashboardStats(
    int ActiveUsers,
    int JobsToday,
    long BytesSaved,
    int OpenIncidents,
    int QuarantinedFiles,
    double LosslessSuccessRate);

public sealed record UserSummary(
    int Id,
    string Email,
    string DisplayName,
    string Role,
    string Status,
    bool MfaEnabled,
    DateTimeOffset CreatedAt,
    DateTimeOffset? LastLogin);

public sealed record CompressionJob(
    string Id,
    string FileName,
    string UserEmail,
    string Mode,
    string Status,
    long OriginalSize,
    long CompressedSize,
    bool IntegrityVerified,
    DateTimeOffset CreatedAt);

public sealed record SecurityIncident(
    string Id,
    string Severity,
    string Type,
    string Resource,
    string Status,
    string Summary,
    DateTimeOffset CreatedAt);

public sealed record QuarantinedFile(
    string Id,
    string FileName,
    string OwnerEmail,
    string ClamAvResult,
    IReadOnlyList<string> YaraMatches,
    string Sha256,
    DateTimeOffset QuarantinedAt);

public sealed record AuditEvent(
    long Id,
    string Actor,
    string Action,
    string Resource,
    string Result,
    string IpAddress,
    DateTimeOffset CreatedAt);

public sealed record ServiceHealth(
    string Name,
    string Status,
    double LatencyMs,
    string Version,
    DateTimeOffset CheckedAt);
