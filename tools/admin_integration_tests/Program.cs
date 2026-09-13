using System.Net;
using System.Security.Cryptography;
using XaiCompress.Admin.Services;

static void Check(bool value) { if(!value) throw new InvalidOperationException("Admin test assertion failed"); }
var session=new AdminSession();
var handler=new FakeHandler();
using var http=new HttpClient(handler){BaseAddress=new Uri("http://127.0.0.1"),Timeout=TimeSpan.FromSeconds(5)};
var client=new PlatformApiClient(http,session);
try { await client.GetDashboardAsync(); throw new Exception("Unauthenticated call accepted"); }
catch(AdminApiAuthorizationException e) { Check(e.StatusCode==HttpStatusCode.Unauthorized); }
Check(handler.Calls==0);
session.SetToken(Convert.ToHexString(RandomNumberGenerator.GetBytes(32)));
handler.Status=HttpStatusCode.Unauthorized;
try { await client.GetUsersAsync(); throw new Exception("Expired call accepted"); }
catch(AdminApiAuthorizationException) { Check(!session.IsAuthenticated); }
session.SetToken(Convert.ToHexString(RandomNumberGenerator.GetBytes(32)));
handler.Fail=true;
try { await client.GetDashboardAsync(); throw new Exception("Backend outage replaced by data"); }
catch(HttpRequestException) { }
Console.WriteLine("ADMIN_CLIENT_ERROR_TESTS = PASS");

using(var authHttp=new HttpClient(new LoginHandler(LoginScenario.Invalid)){BaseAddress=new Uri("http://127.0.0.1")}){
 var authClient=new PlatformApiClient(authHttp,new AdminSession());try{await authClient.LoginAsync("user@example.com","wrong");throw new Exception("Wrong credentials accepted");}catch(AdminApiAuthorizationException){}}
using(var authHttp=new HttpClient(new LoginHandler(LoginScenario.Mfa)){BaseAddress=new Uri("http://127.0.0.1")}){
 var authClient=new PlatformApiClient(authHttp,new AdminSession());try{await authClient.LoginAsync("admin@example.com","correct");throw new Exception("MFA challenge skipped");}catch(AdminMfaRequiredException){}}
using(var authHttp=new HttpClient(new LoginHandler(LoginScenario.NonAdmin)){BaseAddress=new Uri("http://127.0.0.1")}){
 var authClient=new PlatformApiClient(authHttp,new AdminSession());try{await authClient.LoginAsync("user@example.com","correct");throw new Exception("Non-admin accepted");}catch(AdminApiAuthorizationException e){Check(e.StatusCode==HttpStatusCode.Forbidden);}}
var adminSession=new AdminSession();using(var adminHttp=new HttpClient(new LoginHandler(LoginScenario.Admin)){BaseAddress=new Uri("http://127.0.0.1")}){
 var authClient=new PlatformApiClient(adminHttp,adminSession);await authClient.LoginAsync("admin@example.com","correct","123456");Check(adminSession.IsAuthenticated);await authClient.LogoutAsync();Check(!adminSession.IsAuthenticated);}
Console.WriteLine("ADMIN LOGIN, MFA, ROLE AND LOGOUT TESTS = PASS");

var origin=Environment.GetEnvironmentVariable("XAI_ADMIN_TEST_API");
if(string.IsNullOrEmpty(origin))return;
var uri=new Uri(origin);
Check(uri.IsLoopback); // This test harness cannot target production.
using var liveHttp=new HttpClient{BaseAddress=uri,Timeout=TimeSpan.FromSeconds(30)};
var liveSession=new AdminSession();var live=new PlatformApiClient(liveHttp,liveSession);
var email=Environment.GetEnvironmentVariable("XAI_SEED_ADMIN_EMAIL")??throw new Exception("Test email missing");
var password=Environment.GetEnvironmentVariable("XAI_SEED_ADMIN_PASSWORD")??throw new Exception("Test password missing");
await live.LoginAsync(email,password);Check(liveSession.IsAuthenticated);
await live.GetDashboardAsync();
var users=await live.GetUsersAsync();var admin=users.Single(u=>u.Email==email);Check(admin.Role=="admin");
var details=await live.GetUserAsync(admin.Id);Check(details.Email==email);
await live.GetJobsAsync();await live.GetAuditAsync();await live.GetScannerAsync();
var config=await live.GetEmailConfigurationAsync();Check(config.Provider=="mailpit"&&config.DevelopmentOnly);
await live.LogoutAsync();Check(!liveSession.IsAuthenticated);
Console.WriteLine("TEST ADMIN LOGIN = PASS");
Console.WriteLine("ADMIN AUTHORIZATION = PASS");
Console.WriteLine("ADMIN DATA AND LOGOUT = PASS");

sealed class FakeHandler:HttpMessageHandler {
 public int Calls;public bool Fail;public HttpStatusCode Status=HttpStatusCode.OK;
 protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token){
  Calls++;if(Fail)throw new HttpRequestException("Simulated unavailable backend");
  return Task.FromResult(new HttpResponseMessage(Status){Content=new StringContent("{}")});
 }
}
enum LoginScenario{Invalid,Mfa,NonAdmin,Admin}
sealed class LoginHandler(LoginScenario scenario):HttpMessageHandler{
 protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token){
  if(request.RequestUri?.AbsolutePath=="/auth/login"){
   if(scenario==LoginScenario.Invalid)return Reply(HttpStatusCode.Unauthorized,"{\"detail\":\"Invalid credentials\"}");
   if(scenario==LoginScenario.Mfa)return Reply(HttpStatusCode.Unauthorized,"{\"detail\":\"Valid TOTP code required\"}");
   return Reply(HttpStatusCode.OK,"{\"access_token\":\"test-access-token\",\"refresh_token\":\"test-refresh-token\"}");
  }
  if(request.RequestUri?.AbsolutePath=="/admin/stats")return Reply(scenario==LoginScenario.NonAdmin?HttpStatusCode.Forbidden:HttpStatusCode.OK,"{}");
  return Reply(HttpStatusCode.OK,"{}");
 }
 static Task<HttpResponseMessage> Reply(HttpStatusCode status,string json)=>Task.FromResult(new HttpResponseMessage(status){Content=new StringContent(json,System.Text.Encoding.UTF8,"application/json")});
}
