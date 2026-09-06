import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../core/app_state.dart';

class HistoryScreen extends StatelessWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Local history'),
        actions: [
          TextButton.icon(
            onPressed: state.items.isEmpty ? null : state.clearHistory,
            icon: const Icon(Icons.delete_outline),
            label: const Text('Clear'),
          ),
        ],
      ),
      body: state.items.isEmpty
          ? const Center(child: Text('No operations yet.'))
          : ListView.separated(
              padding: const EdgeInsets.all(24),
              itemCount: state.items.length,
              separatorBuilder: (context, index) => const SizedBox(height: 10),
              itemBuilder: (context, index) {
                final item = state.items[index];
                final inputName = item.inputPath.split(RegExp(r'[\\/]')).last;
                final result = item.success
                    ? (item.result == null ? 'Done' : '${item.result!.saving.toStringAsFixed(1)}%')
                    : 'Failed';
                return Card(
                  child: ListTile(
                    leading: CircleAvatar(child: Icon(item.success ? Icons.check : Icons.error_outline)),
                    title: Text('${item.action.toUpperCase()} · $inputName'),
                    subtitle: Text('${item.mode} · ${DateFormat.yMMMd().add_Hm().format(item.createdAt)}\n${item.outputPath}'),
                    isThreeLine: true,
                    trailing: Text(result),
                  ),
                );
              },
            ),
    );
  }
}
