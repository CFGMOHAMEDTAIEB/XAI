import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';import 'package:provider/provider.dart';
import 'package:xai_compress_desktop/main.dart';import 'package:xai_compress_desktop/core/app_state.dart';
import 'package:xai_compress_desktop/services/api_service.dart';import 'package:xai_compress_desktop/services/history_service.dart';
import 'package:xai_compress_desktop/services/local_engine_service.dart';import 'package:xai_compress_desktop/services/settings_service.dart';
void main(){testWidgets('Desktop waits for settings before rendering actions',(tester)async{
 final state=AppState(engine:LocalEngineService(),api:ApiService(),history:HistoryService(),settings:SettingsService());addTearDown(state.dispose);
 await tester.pumpWidget(ChangeNotifierProvider.value(value:state,child:const DesktopApp()));
 expect(find.byType(CircularProgressIndicator),findsOneWidget);expect(tester.takeException(),isNull);
});}
