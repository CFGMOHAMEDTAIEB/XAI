import 'package:desktop_drop/desktop_drop.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

class FileSelector extends StatefulWidget {
  const FileSelector({super.key, required this.value, required this.onChanged, required this.label});

  final String? value;
  final ValueChanged<String?> onChanged;
  final String label;

  @override
  State<FileSelector> createState() => _FileSelectorState();
}

class _FileSelectorState extends State<FileSelector> {
  bool drag = false;

  Future<void> pick() async {
    final result = await FilePicker.platform.pickFiles();
    widget.onChanged(result?.files.single.path);
  }

  @override
  Widget build(BuildContext context) => DropTarget(
        onDragEntered: (_) => setState(() => drag = true),
        onDragExited: (_) => setState(() => drag = false),
        onDragDone: (detail) {
          setState(() => drag = false);
          if (detail.files.isNotEmpty) widget.onChanged(detail.files.first.path);
        },
        child: InkWell(
          onTap: pick,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 150),
            padding: const EdgeInsets.all(30),
            decoration: BoxDecoration(
              color: drag ? Theme.of(context).colorScheme.primaryContainer : null,
              border: Border.all(
                color: drag ? Theme.of(context).colorScheme.primary : Theme.of(context).dividerColor,
                width: 2,
              ),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Row(
              children: [
                const Icon(Icons.file_open, size: 42),
                const SizedBox(width: 18),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(widget.label, style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 5),
                      Text(widget.value ?? 'Drop a file here or click to browse', overflow: TextOverflow.ellipsis),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      );
}
