using Microsoft.AspNetCore.Components;
namespace XaiCompress.Admin.Services;

public abstract class AdminReadPage<T> : ComponentBase where T : class
{
    [Inject] protected PlatformApiClient Api { get; set; } = default!;
    [Inject] protected AdminSession Session { get; set; } = default!;
    [Inject] protected NavigationManager Navigation { get; set; } = default!;
    protected T? Data;
    protected bool Loading;
    protected bool RequiresLogin;
    protected string? Error;
    protected abstract Task<T> FetchAsync();
    protected override Task OnParametersSetAsync() => LoadAsync();
    protected async Task LoadAsync()
    {
        if (Loading) return;
        Data = null; Error = null; RequiresLogin = !Session.IsAuthenticated;
        if (RequiresLogin) { Navigation.NavigateTo("/login"); return; }
        Loading = true;
        try { Data = await FetchAsync(); }
        catch (AdminApiAuthorizationException exception) { RequiresLogin = true; if(exception.StatusCode==System.Net.HttpStatusCode.Unauthorized) Navigation.NavigateTo("/login"); else Error="Access denied."; }
        catch (HttpRequestException e) when (e.StatusCode == System.Net.HttpStatusCode.NotFound) { Error = "Record or endpoint not found."; }
        catch (Exception) { Error = "Data unavailable. The backend may be unreachable or returned an invalid response. Retry when connected."; }
        finally { Loading = false; }
    }
}
