namespace XaiCompress.Admin.Services;

public sealed class AdminSession
{
    public string? AccessToken { get; private set; }
    public string? RefreshToken { get; private set; }
    public bool IsAuthenticated => !string.IsNullOrWhiteSpace(AccessToken);

    public void SetToken(string token, string? refreshToken = null) { AccessToken = token; RefreshToken = refreshToken; }
    public void Clear() { AccessToken = null; RefreshToken = null; }
}
