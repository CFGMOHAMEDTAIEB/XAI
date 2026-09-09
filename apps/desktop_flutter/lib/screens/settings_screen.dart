import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:provider/provider.dart';

import '../core/app_state.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});
  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late TextEditingController python, engine, checkpoint, output, api;
  bool initialized = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (initialized) return;
    initialized = true;
    final config = context.read<AppState>().config;
    python = TextEditingController(text: config.python);
    engine = TextEditingController(text: config.engineDirectory);
    checkpoint = TextEditingController(text: config.checkpoint);
    output = TextEditingController(text: config.outputDirectory);
    api = TextEditingController(text: context.read<AppState>().api.baseUrl);
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(28),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: Column(children: [
            const Text('Privacy and data use — draft: settings and history, including local file paths, are stored on this computer. Cloud operations send file contents and account credentials to the configured API. Clearing local history does not delete server files. Operator retention, contact and deletion procedures are not finalized.'),
            field(python, 'Python executable'),
            field(engine, 'XAI-Compress engine directory', pick: () async {
              final path = await FilePicker.platform.getDirectoryPath();
              if (path != null) engine.text = path;
            }),
            field(checkpoint, 'Neural checkpoint .pt', pick: () async {
              final result = await FilePicker.platform.pickFiles(type: FileType.custom, allowedExtensions: ['pt']);
              if (result != null) checkpoint.text = result.files.single.path ?? '';
            }),
            field(output, 'Default output directory', pick: () async {
              final path = await FilePicker.platform.getDirectoryPath();
              if (path != null) output.text = path;
            }),
            field(api, kReleaseMode ? 'API URL fixed by this release' : 'FastAPI base URL', readOnly: kReleaseMode),
            SwitchListTile(value: state.darkMode, onChanged: state.toggleDark, title: const Text('Dark mode')),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: () async {
                final config = state.config;
                config.python = python.text;
                config.engineDirectory = engine.text;
                config.checkpoint = checkpoint.text;
                config.outputDirectory = output.text;
                config.apiUrl = api.text;
                await state.saveSettings();
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Settings saved')));
                }
              },
              child: const Text('Save settings'),
            ),
          ]),
        ),
      ),
    );
  }

  @override
  void dispose() {
    for (final controller in [python, engine, checkpoint, output, api]) { controller.dispose(); }
    super.dispose();
  }

  Widget field(TextEditingController controller, String label, {VoidCallback? pick, bool readOnly = false}) => Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: TextField(
          controller: controller,
          readOnly: readOnly,
          decoration: InputDecoration(
            labelText: label,
            suffixIcon: pick == null ? null : IconButton(onPressed: pick, icon: const Icon(Icons.folder_open)),
          ),
        ),
      );
}
