namespace XaiCompress.Admin.Models;

public sealed record UserDetails(int Id, string Email, string DisplayName, string Role,
    string Status, bool EmailVerified, bool MfaEnabled,
    DateTimeOffset CreatedAt, DateTimeOffset? LastLogin, int FileCount, string MfaEnrollmentState);
public sealed record ScannerStatus(string Status, string Clamav, string Yara, bool Required);
public sealed record EmailConfiguration(string Provider, bool Configured, string[] Missing,
    [property: System.Text.Json.Serialization.JsonPropertyName("delivery_verified")] bool DeliveryVerified,
    [property: System.Text.Json.Serialization.JsonPropertyName("xaic_supported")] bool XaicSupported,
    [property: System.Text.Json.Serialization.JsonPropertyName("development_only")] bool DevelopmentOnly,
    [property: System.Text.Json.Serialization.JsonPropertyName("api_key")] string ApiKey,
    [property: System.Text.Json.Serialization.JsonPropertyName("sender_configured")] bool SenderConfigured,
    [property: System.Text.Json.Serialization.JsonPropertyName("smtp_security")] string? SmtpSecurity);

public sealed record DashboardStats(
    int ActiveUsers,
    int TotalUsers,
    int PendingVerification,
    int MfaEnabled,
    int AuthenticatorDevices,
    int CompressionJobs,
    int SuccessfulJobs,
    int FailedJobs,
    int SecurityEvents,
    int JobsToday,
    long BytesSaved,
    int? OpenIncidents,
    int? QuarantinedFiles,
    double? LosslessSuccessRate);

public sealed record UserSummary(
    int Id,
    string Email,
    string DisplayName,
    string Role,
    string Status,
    bool EmailVerified,
    bool PhoneVerified,
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

public sealed record AuthenticatorDevice(
    [property: System.Text.Json.Serialization.JsonPropertyName("user_id")] int UserId,
    [property: System.Text.Json.Serialization.JsonPropertyName("device_id")] string DeviceId,
    string Platform,
    [property: System.Text.Json.Serialization.JsonPropertyName("app_version")] string AppVersion,
    string Status,
    [property: System.Text.Json.Serialization.JsonPropertyName("registered_at")] DateTimeOffset RegisteredAt,
    [property: System.Text.Json.Serialization.JsonPropertyName("last_activity")] DateTimeOffset LastActivity);
public sealed record AuthenticatorHistory(
    [property: System.Text.Json.Serialization.JsonPropertyName("user_id")] int UserId,
    string Type, string Result, string Application,
    [property: System.Text.Json.Serialization.JsonPropertyName("created_at")] DateTimeOffset CreatedAt);
public sealed record RecoveryCodeSummary(
    [property: System.Text.Json.Serialization.JsonPropertyName("user_id")] int UserId,
    int Issued, int Used, int Remaining);

public sealed record AdminShare(
    int Id,
    [property: System.Text.Json.Serialization.JsonPropertyName("sender_email")] string SenderEmail,
    [property: System.Text.Json.Serialization.JsonPropertyName("recipient_email")] string RecipientEmail,
    [property: System.Text.Json.Serialization.JsonPropertyName("file_name")] string FileName,
    [property: System.Text.Json.Serialization.JsonPropertyName("created_at")] DateTimeOffset? CreatedAt,
    [property: System.Text.Json.Serialization.JsonPropertyName("expires_at")] DateTimeOffset ExpiresAt,
    string Status,
    [property: System.Text.Json.Serialization.JsonPropertyName("remaining_downloads")] int RemainingDownloads);
