import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/app_state.dart';
import '../services/api_service.dart';

class ReceiveScreen extends StatefulWidget {
 const ReceiveScreen({super.key});
 @override State<ReceiveScreen> createState()=>_ReceiveScreenState();
}
class _ReceiveScreenState extends State<ReceiveScreen> {
 final email=TextEditingController(),password=TextEditingController(),totp=TextEditingController(),code=TextEditingController();
 String result='';bool busy=false,registering=false;
 ApiService get api=>context.read<AppState>().api;
 Future<void> run(Future<void> Function() action) async {
  if(busy)return;setState((){busy=true;result='';});
  try{await action();}on ApiException catch(e){if(mounted)result=e.message;}
  catch(_){if(mounted)result='Operation failed. Check your connection and file permissions, then retry.';}
  finally{if(mounted)setState(()=>busy=false);}
 }
 Future<void> login() async {
  final client=api;final secret=password.text;password.clear();
  if(registering){await client.register(email.text.trim(),secret);}else{await client.login(email.text.trim(),secret,totp:totp.text.trim());}
  if(mounted){totp.clear();result='Signed in. Cloud processing depends on backend and scanner readiness.';}
 }
 Future<void> download() async {
  final client=api;final share=code.text.trim();
  final path=await FilePicker.platform.saveFile(fileName:'shared.xaic');if(path==null||!mounted)return;
  await client.downloadShare(share,path);if(mounted)result='Downloaded. Open Decompress to restore the artifact.';
 }
 Future<void> history() async {
  final rows=await api.history();if(!mounted)return;
  final selected=await showDialog<dynamic>(context:context,builder:(dialog)=>AlertDialog(title:const Text('Cloud history'),content:SizedBox(width:600,height:360,child:ListView(children:[
   if(rows.isEmpty)const Text('No cloud files yet.'),
   for(final row in rows)ListTile(title:Text(row['name'] as String),subtitle:Text(row['status'] as String),onTap:()=>Navigator.pop(dialog,row)),
  ])),actions:[TextButton(onPressed:()=>Navigator.pop(dialog),child:const Text('Close'))]));
  if(selected!=null&&mounted)await downloadHistory(selected);
 }
 Future<void> downloadHistory(dynamic row) async {
  final client=api;final path=await FilePicker.platform.saveFile(fileName:'artifact.xaic');
  if(path==null||!mounted)return;await client.downloadFile(row['id'] as int,path);if(mounted)result='Artifact downloaded.';
 }
 @override Widget build(BuildContext context)=>Scaffold(appBar:AppBar(title:const Text('XAI account and secure files')),body:SingleChildScrollView(padding:const EdgeInsets.all(28),child:ConstrainedBox(constraints:const BoxConstraints(maxWidth:650),child:Column(crossAxisAlignment:CrossAxisAlignment.stretch,children:[
  if(api.token==null)...[
   TextField(controller:email,enabled:!busy,decoration:const InputDecoration(labelText:'Email')),
   TextField(controller:password,enabled:!busy,obscureText:true,decoration:const InputDecoration(labelText:'Password (at least 10 characters)')),
   if(!registering)TextField(controller:totp,enabled:!busy,maxLength:6,decoration:const InputDecoration(labelText:'TOTP code (only when MFA is enabled)')),
   FilledButton(onPressed:busy?null:()=>run(login),child:Text(registering?'Create account':'Sign in')),
   TextButton(onPressed:busy?null:()=>setState(()=>registering=!registering),child:Text(registering?'Sign in instead':'Create account')),
  ]else...[
   const Text('Set up MFA in XAI Authenticator using this same account. Future logins require TOTP after setup is confirmed.'),
   FilledButton(onPressed:busy?null:()=>run(history),child:const Text('Cloud history and downloads')),
   TextField(controller:code,enabled:!busy,decoration:const InputDecoration(labelText:'Share code')),
   FilledButton(onPressed:busy?null:()=>run(()async{await api.redeem(code.text.trim());if(mounted)result='Share available. Download the artifact below.';}),child:const Text('Redeem code')),
   FilledButton(onPressed:busy?null:()=>run(download),child:const Text('Download artifact')),
   TextButton(onPressed:busy?null:()=>run(()async{await api.logout();if(mounted){code.clear();result='Signed out.';}}),child:const Text('Logout')),
  ],
  if(busy)const LinearProgressIndicator(),if(result.isNotEmpty)Text(result),
 ]))));
 @override void dispose(){for(final c in [email,password,totp,code]){c.dispose();}super.dispose();}
}
