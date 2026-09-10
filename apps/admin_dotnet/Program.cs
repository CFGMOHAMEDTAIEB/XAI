using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authentication.OpenIdConnect;
using XaiCompress.Admin.Components;
using XaiCompress.Admin.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents();

builder.Services.AddHttpContextAccessor();
builder.Services.AddMemoryCache();
builder.Services.AddScoped<AdminSession>();

builder.Services.AddHttpClient<PlatformApiClient>((services, client) =>
{
    var configuration = services.GetRequiredService<IConfiguration>();
    client.BaseAddress = new Uri(configuration["PlatformApi:BaseUrl"] ?? "https://xai-1-be9s.onrender.com");
    client.Timeout = TimeSpan.FromSeconds(30);
});

var oidcEnabled = builder.Configuration.GetValue<bool>("Authentication:OidcEnabled");
if (oidcEnabled)
{
    builder.Services
        .AddAuthentication(options =>
        {
            options.DefaultScheme = CookieAuthenticationDefaults.AuthenticationScheme;
            options.DefaultChallengeScheme = OpenIdConnectDefaults.AuthenticationScheme;
        })
        .AddCookie()
        .AddOpenIdConnect(options =>
        {
            options.Authority = builder.Configuration["Authentication:Authority"];
            options.ClientId = builder.Configuration["Authentication:ClientId"];
            options.ClientSecret = builder.Configuration["Authentication:ClientSecret"];
            options.ResponseType = "code";
            options.SaveTokens = true;
            options.GetClaimsFromUserInfoEndpoint = true;
            options.RequireHttpsMetadata = !builder.Environment.IsDevelopment()
                || builder.Configuration.GetValue("Authentication:RequireHttpsMetadata", true);
        });
    builder.Services.AddAuthorization();
}
else
{
    builder.Services.AddAuthorization();
}

var app = builder.Build();

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/error");
    app.UseHsts();
}

app.UseHttpsRedirection();
app.UseStaticFiles();
app.UseAntiforgery();

if (oidcEnabled)
{
    app.UseAuthentication();
    app.UseAuthorization();
}

app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

app.MapGet("/health", () => Results.Ok(new
{
    status = "ok",
    service = "xai-admin-dotnet",
    utc = DateTimeOffset.UtcNow
}));

app.Run();
