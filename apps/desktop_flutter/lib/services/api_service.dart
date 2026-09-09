import 'dart:async';
import 'dart:io';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'deployment_config.dart';

class ApiException implements Exception {
  const ApiException(this.message);
  final String message;
  @override String toString()=>message;
}
class ApiService {
  ApiService({http.Client? client}):_client=client??http.Client();
  final http.Client _client;
  String baseUrl=configuredApiUrl();
  String? token;
  String? _refreshToken;
  Future<void>? _refreshing;
  int _generation=0;
  Future<void> login(String email,String password,{String?totp}) async {
    final generation=_generation;
    final response=await _json('/auth/login',body:{'email':email,'password':password,'totp_code':totp?.isEmpty==true?null:totp});
    if(generation!=_generation)throw const ApiException('Session changed. Sign in again.');
    final data=jsonDecode(response.body);
    token=data['access_token'] as String;
    _refreshToken=data['refresh_token'] as String?;
  }
  Future<void> register(String email,String password) async {
    final generation=_generation;
    final response=await _json('/auth/register',body:{'email':email,'password':password});
    if(generation!=_generation)throw const ApiException('Session changed. Sign in again.');
    final data=jsonDecode(response.body);
    token=data['access_token'] as String;
    _refreshToken=data['refresh_token'] as String?;
  }
  Future<void> logout() async {
    final refresh=_refreshToken;
    _generation++;token=null;_refreshToken=null;
    if(refresh==null)return;
    try{await _json('/auth/logout',body:{'refresh_token':refresh});}on ApiException{/* Local session is already cleared. */}
  }
  Future<void> _refresh() => _refreshing??=_rotate().whenComplete(()=>_refreshing=null);
  Future<void> _rotate() async {
    final generation=_generation;
    try{
      if(_refreshToken==null)throw const ApiException('Sign in again.');
      final r=await _json('/auth/refresh',body:{'refresh_token':_refreshToken});
      if(generation!=_generation)throw const ApiException('Session changed. Sign in again.');
      final data=jsonDecode(r.body);token=data['access_token'];_refreshToken=data['refresh_token'];
    }catch(_){if(generation==_generation){token=null;_refreshToken=null;}throw const ApiException('Session expired. Sign in again.');}
  }
  Future<http.Response> _send(Future<http.Response> Function() action,{bool authenticated=true}) async {
    try{
      var r=await action().timeout(const Duration(minutes:10));
      if(r.statusCode==401&&authenticated&&_refreshToken!=null){await _refresh();r=await action().timeout(const Duration(minutes:10));}
      if(r.statusCode>=400){
        if(r.statusCode==401&&authenticated){token=null;_refreshToken=null;}
        throw ApiException(switch(r.statusCode){
          401=>'Sign in again. Check your password and current TOTP if MFA is enabled.',
          403=>'This action is not permitted for this account.',
          409=>'Account or file state changed. Refresh and retry.',
          422=>'Check your input or file. Passwords require at least 10 characters.',
          429=>'Too many requests. Wait before retrying.',
          503=>'Backend or security scanner unavailable. Retry later.',
          _=>'Request failed. Check the file or code and retry.',
        });
      }
      return r;
    }on ApiException{rethrow;}on TimeoutException{throw const ApiException('Request timed out. Check history before repeating an operation.');}
    catch(_){throw const ApiException('Could not complete the request. Check your connection and retry.');}
  }
  Future<http.Response> _json(String path,{Map<String,dynamic>?body}) => _send((){
    final headers={'content-type':'application/json',if(token!=null)'authorization':'Bearer $token'};
    return (body==null?_client.get(Uri.parse('$baseUrl$path'),headers:headers):_client.post(Uri.parse('$baseUrl$path'),headers:headers,body:jsonEncode(body))).timeout(const Duration(seconds:40));
  },authenticated:!RegExp(r'^/auth/(login|register|refresh|logout)$').hasMatch(path));
  Future<List<dynamic>> history() async => jsonDecode((await _json('/history')).body) as List<dynamic>;
  Future<Map<String,dynamic>> redeem(String code) async => Map<String,dynamic>.from(jsonDecode((await _json('/shares/redeem',body:{'code':code})).body));
  Future<http.Response> _upload(String path,String input) => _send(() async {
    if(token==null)throw const ApiException('Sign in before using cloud operations.');
    final request=http.MultipartRequest('POST',Uri.parse('$baseUrl$path'));
    request.headers['authorization']='Bearer $token';
    request.files.add(await http.MultipartFile.fromPath('upload',input));
    return http.Response.fromStream(await _client.send(request));
  });
  Future<void> downloadFile(int id,String output) async {
    final r=await _send(()=>_client.get(Uri.parse('$baseUrl/files/$id/download'),headers:{'authorization':'Bearer $token'}));
    await File(output).writeAsBytes(r.bodyBytes);
  }
  Future<Map<String,dynamic>> compress(String input,String output) async {
    final r=await _upload('/compression/jobs',input);
    final job=Map<String,dynamic>.from(jsonDecode(r.body));
    await downloadFile(job['id'] as int,output);
    return {'original_size':job['original_size'],'artifact_size':job['compressed_size'],'mode':job['codec'],'sha256':job['sha256']};
  }
  Future<Map<String,dynamic>> decompress(String input,String output) async {
    final r=await _upload('/compression/decompress',input);
    await File(output).writeAsBytes(r.bodyBytes);
    return {'restored_size':r.bodyBytes.length,'mode':'cloud-decompress','sha256':r.headers['x-content-sha256']};
  }
  Future<void> downloadShare(String code,String output) async {
    final r=await _json('/shares/download',body:{'code':code});
    await File(output).writeAsBytes(r.bodyBytes);
  }
  void dispose()=>_client.close();
}
