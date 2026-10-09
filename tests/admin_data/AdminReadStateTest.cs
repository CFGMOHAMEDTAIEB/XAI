using System.Net;
using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.Logging.Abstractions;
using XaiCompress.Admin.Services;

internal static class AdminReadStateTest
{
    public static async Task RunAsync()
    {
        var session = new AdminSession();
        session.SetToken("read-state-access", "read-state-refresh");
        var page = new TestPage(session);
        page.Next = () => throw new HttpRequestException("Simulated failure", null, HttpStatusCode.InternalServerError);
        await page.ReadAsync();
        if (page.CurrentData is not null || page.CurrentError is null || page.IsLoading)
            throw new InvalidOperationException("A failed Admin read did not expose a safe error state.");

        page.Next = () => Task.FromResult<IReadOnlyList<string>>([]);
        await page.ReadAsync();
        if (page.CurrentData is null || page.CurrentData.Count != 0 || page.CurrentError is not null || page.IsLoading)
            throw new InvalidOperationException("An empty successful Admin read retained a stale error.");

        page.Next = () => Task.FromResult<IReadOnlyList<string>>(["record"]);
        await page.ReadAsync();
        if (page.CurrentData?.Count != 1 || page.CurrentError is not null || page.IsLoading)
            throw new InvalidOperationException("A populated successful Admin read did not replace the empty state.");
    }

    private sealed class TestPage : AdminReadPage<IReadOnlyList<string>>
    {
        public TestPage(AdminSession session)
        {
            Session = session;
            Navigation = new TestNavigation();
            Logger = NullLogger<AdminReadPage<IReadOnlyList<string>>>.Instance;
        }
        public Func<Task<IReadOnlyList<string>>> Next { get; set; } = default!;
        public IReadOnlyList<string>? CurrentData => Data;
        public string? CurrentError => Error;
        public bool IsLoading => Loading;
        public Task ReadAsync() => LoadAsync();
        protected override Task<IReadOnlyList<string>> FetchAsync() => Next();
    }

    private sealed class TestNavigation : NavigationManager
    {
        public TestNavigation() => Initialize("http://localhost:15051/", "http://localhost:15051/jobs");
        protected override void NavigateToCore(string uri, bool forceLoad) { }
    }
}
