import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/app_state.dart';
import '../widgets/file_selector.dart';
import '../widgets/result_card.dart';

class DecompressScreen extends StatelessWidget {
  const DecompressScreen({super.key});

  Future<void> selectOutput(BuildContext context) async {
    final path = await FilePicker.platform.saveFile(dialogTitle: 'Save restored file', fileName: 'restored.bin');
    if (!context.mounted) return;
    context.read<AppState>().selectOutput(path);
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Scaffold(
      appBar: AppBar(title: const Text('Verified decompression')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(28),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Restore a .xaic file', style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: 6),
          const Text('The engine rejects corruption, wrong checkpoints and invalid output sizes.'),
          const SizedBox(height: 24),
          FileSelector(value: state.inputPath, onChanged: state.selectInput, label: 'Compressed .xaic file'),
          const SizedBox(height: 18),
          OutlinedButton.icon(
            onPressed: () => selectOutput(context),
            icon: const Icon(Icons.save),
            label: Text(state.outputPath ?? 'Select restored output'),
          ),
          const SizedBox(height: 20),
          if (state.processing) ...[
            const LinearProgressIndicator(),
            Text(state.status),
            if (state.mode != 'cloud') TextButton(onPressed: state.cancel, child: const Text('Cancel')),
          ] else
            FilledButton.icon(
              onPressed: state.inputPath != null && state.outputPath != null ? state.decompress : null,
              icon: const Icon(Icons.unarchive),
              label: const Text('Decompress and verify'),
            ),
          if (!state.processing && state.status != 'Ready') Text(state.status),
          if (state.lastResult != null) ...[
            const SizedBox(height: 24),
            ResultCard(result: state.lastResult!),
          ],
        ]),
      ),
    );
  }
}
