import '../services/deployment_config.dart';
import 'dart:async';import 'package:flutter/foundation.dart';import '../models/app_models.dart';import '../services/api_service.dart';import '../services/history_service.dart';import '../services/local_engine_service.dart';import '../services/settings_service.dart';
class AppState extends ChangeNotifier{AppState({required this.engine,required this.api,required this.history,required this.settings});final LocalEngineService engine;final ApiService api;final HistoryService history;final SettingsService settings;bool loading=true,processing=false,darkMode=false;int page=0;double progress=0;String status='Ready';String?inputPath,outputPath;String mode='cloud';EngineResult?lastResult;List<HistoryItem>items=[];late DesktopSettings config;
 Future<void>initialize()async{
 config=DesktopSettings();
 try{config=await settings.load().timeout(const Duration(seconds:15));api.baseUrl=kReleaseMode?configuredApiUrl():config.apiUrl;darkMode=config.darkMode;items=await history.load().timeout(const Duration(seconds:15));}
 catch(_){status='Could not restore local settings or history. Check file permissions and restart.';}
 finally{loading=false;notifyListeners();}
 }void setPage(int x){page=x;notifyListeners();}void selectInput(String?x){inputPath=x;notifyListeners();}void selectOutput(String?x){outputPath=x;notifyListeners();}void setMode(String x){mode=x;notifyListeners();}
 Future<void>compress()async{if(processing)return;if(mode=='cloud'){await _cloud(false);return;}if(inputPath==null||outputPath==null)return;await _consume(engine.compress(python:config.python,workingDirectory:config.engineDirectory,input:inputPath!,output:outputPath!,mode:mode,checkpoint:config.checkpoint),'compress');}Future<void>decompress()async{if(processing)return;if(mode=='cloud'){await _cloud(true);return;}if(inputPath==null||outputPath==null)return;await _consume(engine.decompress(python:config.python,workingDirectory:config.engineDirectory,input:inputPath!,output:outputPath!,checkpoint:config.checkpoint),'decompress');}
 Future<void>_cloud(bool restore)async{
 if(processing||inputPath==null||outputPath==null)return;
 processing=true;lastResult=null;status='Processing on backend...';notifyListeners();
 try{final result=restore?await api.decompress(inputPath!,outputPath!):await api.compress(inputPath!,outputPath!);lastResult=EngineResult.fromJson(result);status='Completed';
 final item=HistoryItem(id:DateTime.now().microsecondsSinceEpoch.toString(),action:restore?'decompress':'compress',inputPath:inputPath!,outputPath:outputPath!,mode:'cloud',createdAt:DateTime.now(),success:true,result:lastResult);items=[item,...items];await history.save(items);
 }catch(e){status='$e';lastResult=null;}finally{processing=false;notifyListeners();}}
 Future<void>_consume(Stream<ProcessUpdate>s,String action)async{
 processing=true;status='Starting...';progress=.15;lastResult=null;notifyListeners();String?error;
 try{
 await for(final u in s.timeout(const Duration(minutes:10))){status=u.message;progress=u.done?1:(progress+.08).clamp(0.0,.9);lastResult=u.result;error=u.error??error;notifyListeners();}
 final item=HistoryItem(id:DateTime.now().microsecondsSinceEpoch.toString(),action:action,inputPath:inputPath!,outputPath:outputPath!,mode:mode,createdAt:DateTime.now(),success:error==null&&lastResult!=null,result:lastResult,error:error??(lastResult==null?'No verified result returned':null));items=[item,...items];await history.save(items);
 }catch(_){engine.cancel();status='Local operation failed or timed out. Check the engine configuration and retry.';lastResult=null;}
 finally{processing=false;notifyListeners();}
 }void cancel(){engine.cancel();processing=false;status='Cancelled';notifyListeners();}Future<void>clearHistory()async{items=[];await history.clear();notifyListeners();}Future<void>saveSettings()async{config.darkMode=darkMode;api.baseUrl=kReleaseMode?configuredApiUrl():config.apiUrl;await settings.save(config);notifyListeners();}void toggleDark(bool x){darkMode=x;notifyListeners();}}
