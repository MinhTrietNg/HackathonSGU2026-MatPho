library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_sheet.dart';
import '../../core/widgets/mp_text_field.dart';
import '../../data/models/camera.dart';
import '../../data/providers.dart';
import '../groups/group_state.dart' show groupAreasProvider;
import 'camera_state.dart';
import 'camera_widgets.dart';

Future<Area?> showNewAreaSheet(
  BuildContext context, {
  String initialName = '',
  bool previewFocused = false,
}) {
  final container = ProviderScope.containerOf(context, listen: false);
  return showMpSheet<Area>(
    context,
    builder: (_) => UncontrolledProviderScope(
      container: container,
      child: NewAreaSheet(
        initialName: initialName,
        previewFocused: previewFocused,
      ),
    ),
  );
}

const newAreaPlaceholder = 'Bãi ô tô ngoài trời';

class NewAreaSheet extends ConsumerStatefulWidget {
  const NewAreaSheet({
    super.key,
    this.initialName = '',
    this.previewFocused = false,
  });

  final String initialName;

  final bool previewFocused;

  @override
  ConsumerState<NewAreaSheet> createState() => _NewAreaSheetState();
}

class _NewAreaSheetState extends ConsumerState<NewAreaSheet> {
  late final _name = TextEditingController(text: widget.initialName);
  bool _busy = false;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _create() async {
    final name = _name.text.trim();
    if (name.isEmpty) return;
    setState(() => _busy = true);
    try {
      final group = await ref.read(addCameraPlaceProvider.future);
      final area = await ref
          .read(cameraRepositoryProvider)
          .createArea(groupId: group.id, name: name);
      ref.invalidate(groupAreasProvider(group.id));
      if (mounted) Navigator.of(context).pop(area);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return CameraSheet(
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 24),
      spacing: 14,
      handleColor: c.lineStrong,
      centerHandle: true,
      children: [
        Semantics(
          header: true,
          child: Text(
            'Khu vực mới',
            style: t.headline.copyWith(
              fontWeight: FontWeight.w700,
              color: c.textPrimary,
            ),
          ),
        ),
        Text(
          'Ví dụ: Hầm B1, Sảnh tầng 1.',
          style: t.caption.copyWith(
            fontWeight: FontWeight.w500,
            color: c.textSecondary,
          ),
        ),
        MpTextField(
          label: 'Tên khu vực',
          icon: MpIcons.edit,
          controller: _name,
          hintText: newAreaPlaceholder,
          textInputAction: TextInputAction.done,
          onSubmitted: (_) => _create(),
          state: widget.previewFocused ? MpFieldState.focused : null,
        ),
        MpButton(label: 'Tạo khu vực', onPressed: _busy ? null : _create),
      ],
    );
  }
}
