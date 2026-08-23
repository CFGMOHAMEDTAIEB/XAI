namespace XaiCompress.Admin.Services;

public sealed class AdminSession
{
    public string? AccessToken { get; private set; }
    public bool IsAuthenticated => !string.IsNullOrWhiteSpace(AccessToken);

    public void SetToken(string token) => AccessToken = token;
    public void Clear() => AccessToken = null;
}
