using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.Logging;
namespace XaiCompress.Admin.Services;

public abstract class AdminReadPage<T> : ComponentBase where T : class
{
    [Inject] protected PlatformApiClient Api { get; set; } = default!;
    [Inject] protected AdminSession Session { get; set; } = default!;
    [Inject] protected NavigationManager Navigation { get; set; } = default!;
    [Inject] protected ILogger<AdminReadPage<T>> Logger { get; set; } = default!;
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
        if (RequiresLogin) { RedirectToLogin(); return; }
        Loading = true;
        try
        {
            Data = await FetchAsync();
            if (Data is null) throw new InvalidOperationException("The administrator read returned no data.");
            Error = null;
        }
        catch (AdminApiAuthorizationException exception) when (exception.StatusCode == System.Net.HttpStatusCode.Unauthorized)
        {
            LogReadFailure((int)exception.StatusCode, "Unauthorized");
            RequiresLogin = !Session.IsAuthenticated;
            if (RequiresLogin) RedirectToLogin();
            else Error = "We couldn't verify this administrator session. Please try again.";
        }
        catch (AdminApiAuthorizationException exception)
        {
            LogReadFailure((int)exception.StatusCode, "Forbidden");
            Error = "You do not have permission to access this administrator resource.";
        }
        catch (HttpRequestException exception) when (exception.StatusCode == System.Net.HttpStatusCode.NotFound)
        {
            LogReadFailure((int)exception.StatusCode, "NotFound");
            Error = "The requested administrator resource was not found.";
        }
        catch (HttpRequestException exception) when (exception.StatusCode == System.Net.HttpStatusCode.Conflict)
        {
            LogReadFailure((int)exception.StatusCode, "Conflict");
            Error = "The requested change conflicts with the current account state.";
        }
        catch (OperationCanceledException)
        {
            LogReadFailure(null, "TimedOut");
            Error = "This request timed out. Please try again.";
        }
        catch (HttpRequestException exception)
        {
            LogReadFailure(exception.StatusCode is null ? null : (int)exception.StatusCode, "RequestFailed");
            Error = "We couldn't load this information. Please try again.";
        }
        catch (Exception exception)
        {
            LogReadFailure(null, exception.GetType().Name);
            Error = "We couldn't load this information. Please try again.";
        }
        finally { Loading = false; }
    }

    protected void LogReadFailure(int? status, string reason, string? endpoint = null)
    {
        var page = GetType().Name;
        endpoint ??= page switch
        {
            "Users" => "/admin/users",
            "UserDetails" => "/admin/users/{id}",
            "Jobs" => "/admin/jobs",
            "Shares" => "/admin/shares",
            "Audit" => "/admin/audit",
            "Authenticator" => "/admin/authenticator/devices",
            "Scanner" => "/admin/security/scanner",
            "Email" => "/admin/email/configuration",
            "SystemHealth" => "/health and admin readiness",
            _ => "unknown"
        };
        Logger.LogWarning("Admin read failed Page={Page} Endpoint={Endpoint} Status={Status} Reason={Reason}",
            page, endpoint, status, reason);
    }

    protected void RedirectToLogin() =>
        Navigation.NavigateTo(Session.State == AdminSessionState.Expired ? "/login?expired=1" : "/login");
}
