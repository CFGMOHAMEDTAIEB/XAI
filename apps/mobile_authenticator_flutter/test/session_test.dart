import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:xai_compress_authenticator/services/api_service.dart';
void main(){
 test('Concurrent expiry rotates once and logout revokes the rotated token',()async{
  var refreshes=0;String? revoked;
  final api=ApiService(client:MockClient((request)async{
   switch(request.url.path){
    case '/auth/login':return http.Response(jsonEncode({'access_token':'old','refresh_token':'refresh-old'}),200);
    case '/auth/refresh':refreshes++;await Future<void>.delayed(const Duration(milliseconds:20));return http.Response(jsonEncode({'access_token':'new','refresh_token':'refresh-new'}),200);
    case '/auth/logout':revoked=jsonDecode(request.body)['refresh_token'];return http.Response('{}',200);
    default:return request.headers['authorization']=='Bearer new'?http.Response('{"state":"enabled"}',200):http.Response('{}',401);
   }
  }));
  await api.login(email:'user@example.com',password:'test-password');
  await Future.wait([api.mfaStatus(),api.mfaStatus()]);
  expect(refreshes,1);await api.logout();expect(revoked,'refresh-new');expect(api.accessToken,isNull);api.dispose();
 });
 test('Failed refresh clears the session and never loops',()async{
  var refreshes=0;
  final api=ApiService(client:MockClient((request)async{
   if(request.url.path=='/auth/login')return http.Response('{"access_token":"old","refresh_token":"r"}',200);
   if(request.url.path=='/auth/refresh')refreshes++;
   return http.Response('{}',401);
  }));
  await api.login(email:'user@example.com',password:'test-password');
  await expectLater(api.mfaStatus(),throwsA(isA<ApiException>()));expect(refreshes,1);expect(api.accessToken,isNull);api.dispose();
 });
}
