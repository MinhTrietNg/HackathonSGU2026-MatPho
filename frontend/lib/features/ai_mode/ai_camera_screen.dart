library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_page.dart';
import '../../core/widgets/mp_section_label.dart';
import '../../data/errors.dart';
import '../../data/models/models.dart';
import '../groups/group_state.dart';
import '../groups/group_widgets.dart';
import 'ai_mode_state.dart';
import 'ai_mode_widgets.dart';

class AiCameraScreen extends ConsumerStatefulWidget {
  const AiCameraScreen({super.key, required this.cameraId});

  final String cameraId;

  @override
  ConsumerState<AiCameraScreen> createState() => _AiCameraScreenState();
}

class _AiCameraScreenState extends ConsumerState<AiCameraScreen> {
  CameraAi? _draft;
  bool _busy = false;

  Future<void> _save(Camera camera, CameraAi draft) async {
    setState(() => _busy = true);
    try {
      await ref
          .read(aiModeActionsProvider)
          .save(
            camera,
            draft.mode == AiMode.scheduled ? draft : CameraAi(mode: draft.mode),
          );
      if (mounted) context.pop();
    } on MpException catch (e) {
      if (!mounted) return;
      setState(() => _busy = false);
      showGroupFailureToast(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final view = ref.watch(aiCameraProvider(widget.cameraId)).value;
    final draft = _draft ?? view?.camera.ai;
    final valid =
        draft != null &&
        (draft.mode != AiMode.scheduled || draft.pauses.every(aiPauseValid));

    return MpPage(
      header: MpHeader.back(
        title: view?.camera.name ?? '',
        onBack: () => context.pop(),
      ),
      headerBottom: 14,
      gap: 14,
      children: [
        if (view != null && draft != null) ...[
          MpSectionLabel(
            '${shortGroupName(groupDisplayName(view.group)).toUpperCase()}'
            ' · AI NHẬN DIỆN CHÁY',
          ),
          AiModePicker(
            value: draft,
            onChanged: (ai) => setState(() => _draft = ai),
          ),
        ],
        const Spacer(),
        MpButton(
          label: 'Lưu',
          onPressed: _busy || !valid || view == null
              ? null
              : () => _save(view.camera, draft),
        ),
      ],
    );
  }
}
