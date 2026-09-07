import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:xai_compress_desktop/services/api_service.dart';

void main(){
 test('Desktop cloud adapter uploads, downloads and restores real bytes',()async{
  final api=ApiService();
  final tag=DateTime.now().microsecondsSinceEpoch.toString();
  final email='desktop-live-$tag@example.com';
  final password=List.generate(32,(_)=>Random.secure().nextInt(10)).join();
  final registration=await http.post(Uri.parse('${api.baseUrl}/auth/register'),headers:{'content-type':'application/json'},body:jsonEncode({'email':email,'password':password}));
  expect(registration.statusCode,200);
  await api.login(email,password);
  final dir=await Directory.systemTemp.createTemp('xai-desktop-live-');
  try{
   final original=List<int>.generate(32768,(i)=>i%256);
   final input=File('${dir.path}/original.bin');await input.writeAsBytes(original);
   final compressed='${dir.path}/original.bin.xaic';final restored='${dir.path}/restored.bin';
   final job=await api.compress(input.path,compressed);
   expect(job['original_size'],original.length);
   await api.decompress(compressed,restored);
   expect(listEquals(original,await File(restored).readAsBytes()),isTrue);
  }finally{await dir.delete(recursive:true);}
 },skip:!const bool.fromEnvironment('XAI_LIVE_TEST'),timeout:const Timeout(Duration(minutes:10)));
}
