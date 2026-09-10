import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/app_state.dart';
import '../widgets/account_code_card.dart';
import 'add_account_screen.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Scaffold(
      appBar: AppBar(title: const Text('XAI'), actions: [
        IconButton(onPressed: state.lock, icon: const Icon(Icons.lock_outline), tooltip: 'Lock'),
      ]),
      floatingActionButton: FloatingActionButton.extended(onPressed:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>const AddAccountScreen())),icon:const Icon(Icons.add),label:const Text('Add account')),
      body: ListView(padding: const EdgeInsets.fromLTRB(16,16,16,96), children: [
        Semantics(label:'Security status: app unlocked',child:Card(child:ListTile(leading:const Icon(Icons.verified_user_outlined),title:const Text('Authenticator protected'),subtitle:const Text('TOTP works offline. Push approvals require a network connection.')))),
        const SizedBox(height: 24),Text('Authenticator accounts',style:Theme.of(context).textTheme.titleLarge),const SizedBox(height:12),
        if (state.accounts.isEmpty) const Card(child:Padding(padding:EdgeInsets.all(24),child:Column(children:[Icon(Icons.key_outlined,size:36),SizedBox(height:12),Text('No accounts yet'),SizedBox(height:6),Text('Add an account by scanning the QR code issued by the service.',textAlign:TextAlign.center)]))),
        for (final account in state.accounts)
          Padding(padding: const EdgeInsets.only(bottom: 12), child: AccountCodeCard(account: account)),
      ]),
    );
  }
}
