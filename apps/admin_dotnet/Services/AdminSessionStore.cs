using Microsoft.AspNetCore.Components.Server.ProtectedBrowserStorage;

namespace XaiCompress.Admin.Services;

public sealed record StoredAdminSession(string AccessToken, string RefreshToken,
    bool AuthenticationPending = false);

public interface IAdminSessionStore
{
    Task<StoredAdminSession?> ReadAsync();
    Task WriteAsync(StoredAdminSession session);
    Task DeleteAsync();
}

public sealed class ProtectedAdminSessionStore(ProtectedSessionStorage storage) : IAdminSessionStore
{
    private const string StorageKey = "xaicd.admin.session.v1";

    public async Task<StoredAdminSession?> ReadAsync()
    {
        var result = await storage.GetAsync<StoredAdminSession>(StorageKey);
        return result.Success ? result.Value : null;
    }

    public Task WriteAsync(StoredAdminSession session) => storage.SetAsync(StorageKey, session).AsTask();
    public Task DeleteAsync() => storage.DeleteAsync(StorageKey).AsTask();
}
