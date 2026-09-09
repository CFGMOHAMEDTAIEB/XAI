import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:xai_compress_desktop/services/api_service.dart';
void main(){
 test('Concurrent protected calls rotate once; logout clears and revokes',()async{
  var refreshes=0;String? revoked;
  final api=ApiService(client:MockClient((request)async{
   switch(request.url.path){
    case '/auth/login':return http.Response('{"access_token":"old","refresh_token":"r"}',200);
    case '/auth/refresh':refreshes++;await Future<void>.delayed(const Duration(milliseconds:20));return http.Response('{"access_token":"new","refresh_token":"rotated"}',200);
    case '/auth/logout':revoked=jsonDecode(request.body)['refresh_token'];return http.Response('{}',200);
    default:return request.headers['authorization']=='Bearer new'?http.Response('[]',200):http.Response('private-response',401);
   }
  }));
  await api.login('user@example.com','test-password');await Future.wait([api.history(),api.history()]);
  expect(refreshes,1);await api.logout();expect(revoked,'rotated');expect(api.token,isNull);api.dispose();
 });
 test('Provider errors never reach desktop UI',()async{
  final api=ApiService(client:MockClient((request)async=>http.Response('private-response',503)));
  try{await api.history();fail('must fail');}on ApiException catch(e){expect(e.toString(),isNot(contains('private-response')));}
  api.dispose();
 });
}
