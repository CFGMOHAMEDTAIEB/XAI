import 'dart:io';
import 'deployment_config.dart';
import 'dart:convert';import 'package:http/http.dart'as http;
class ApiService{String baseUrl=configuredApiUrl();String?token;Future<void>login(String email,String password,{String?totp})async{final r=await http.post(Uri.parse('$baseUrl/auth/login'),headers:{'content-type':'application/json'},body:jsonEncode({'email':email,'password':password,'totp_code':totp}));if(r.statusCode>=400)throw Exception(r.body);token=jsonDecode(r.body)['access_token'];}Future<List<dynamic>>history()async{final r=await http.get(Uri.parse('$baseUrl/history'),headers:{'authorization':'Bearer $token'});if(r.statusCode>=400)throw Exception(r.body);return jsonDecode(r.body);}Future<Map<String,dynamic>>redeem(String code)async{final r=await http.post(Uri.parse('$baseUrl/shares/redeem'),headers:{'content-type':'application/json','authorization':'Bearer $token'},body:jsonEncode({'code':code}));if(r.statusCode>=400)throw Exception(r.body);return Map<String,dynamic>.from(jsonDecode(r.body));}
Future<Map<String,dynamic>> compress(String input,String output) async {
  if(token==null) throw StateError('Sign in before cloud compression.');
  final request=http.MultipartRequest('POST',Uri.parse('$baseUrl/compression/jobs'));
  request.headers['authorization']='Bearer $token';
  request.files.add(await http.MultipartFile.fromPath('upload',input));
  final response=await http.Response.fromStream(await request.send().timeout(const Duration(minutes:10)));
  if(response.statusCode>=400)throw Exception(response.body);
  final job=Map<String,dynamic>.from(jsonDecode(response.body));
  final download=await http.get(Uri.parse('$baseUrl/files/${job['id']}/download'),headers:{'authorization':'Bearer $token'}).timeout(const Duration(minutes:10));
  if(download.statusCode>=400)throw Exception(download.body);
  await File(output).writeAsBytes(download.bodyBytes);
  return {'original_size':job['original_size'],'artifact_size':job['compressed_size'],'mode':job['codec'],'sha256':job['sha256']};
}
Future<Map<String,dynamic>> decompress(String input,String output) async {
  if(token==null)throw StateError('Sign in before cloud decompression.');
  final request=http.MultipartRequest('POST',Uri.parse('$baseUrl/compression/decompress'));
  request.headers['authorization']='Bearer $token';request.files.add(await http.MultipartFile.fromPath('upload',input));
  final response=await http.Response.fromStream(await request.send().timeout(const Duration(minutes:10)));
  if(response.statusCode>=400)throw Exception(response.body);
  await File(output).writeAsBytes(response.bodyBytes);
  return {'restored_size':response.bodyBytes.length,'mode':'cloud-decompress','sha256':response.headers['x-content-sha256']};
}
Future<void> downloadShare(String code,String output)async{
 final r=await http.post(Uri.parse('$baseUrl/shares/download'),headers:{'content-type':'application/json','authorization':'Bearer $token'},body:jsonEncode({'code':code}));
 if(r.statusCode>=400)throw Exception(r.body);await File(output).writeAsBytes(r.bodyBytes);
}
}
