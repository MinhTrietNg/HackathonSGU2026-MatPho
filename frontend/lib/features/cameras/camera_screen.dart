library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/time_format.dart';
import '../../core/widgets/mp_banner.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../core/widgets/mp_page.dart';
import '../../core/widgets/mp_tips_card.dart';
import '../../core/widgets/mp_toast.dart';
import '../../data/errors.dart';
import '../../data/models/models.dart';
import '../../data/providers.dart';
import '../groups/group_state.dart' show groupCamerasProvider;
import 'camera_state.dart';
import 'camera_widgets.dart';

class CameraScreen extends ConsumerWidget {
  const CameraScreen({super.key, required this.cameraId});

  final String cameraId;

  void _back(BuildContext context) {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(AppRoutes.monitor);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(cameraDetailProvider(cameraId)).value;
    final lost = detail?.camera.status == CameraStatus.signalLost;
    if (detail != null && !lost) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (context.mounted) context.go(AppRoutes.watch(cameraId));
      });
    }
    return MpPage(
      header: MpHeader.back(
        title: detail?.title ?? '',
        onBack: () => _back(context),
      ),
      headerBottom: 12,
      children: [if (lost) Expanded(child: _SignalLost(detail!))],
    );
  }
}

class _SignalLost extends ConsumerStatefulWidget {
  const _SignalLost(this.detail);

  final CameraDetail detail;

  @override
  ConsumerState<_SignalLost> createState() => _SignalLostState();
}

// I8: a failed "Thử kết nối lại" shows "Vẫn chưa kết nối được"; from the
// second failure, owners and managers also get "Thêm lại RTSP" (I2 → I5 sends
// a new link for this same camera).
class _SignalLostState extends ConsumerState<_SignalLost> {
  bool _busy = false;

  int _failures = 0;

  static const _replaceAfter = 2;

  Future<void> _reconnect() async {
    setState(() => _busy = true);
    final id = widget.detail.camera.id;
    var fixed = false;
    try {
      final camera = await ref.read(cameraRepositoryProvider).reconnect(id);
      fixed = camera.status != CameraStatus.signalLost;
      ref
        ..invalidate(groupCamerasProvider(widget.detail.group.id))
        ..invalidate(cameraDetailProvider(id));
    } on MpException {
      // Still down: stay on I8.
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          if (!fixed) _failures++;
        });
      }
    }
    if (!fixed && mounted) _showStillDown();
  }

  void _showStillDown() {
    final c = context.mpColors;
    showMpToast(
      context,
      MpToast(
        icon: MpDuotoneIcon(
          MpIcons.wifiOff,
          outline: c.statusWarn,
          accent: c.statusWarn,
          size: 18,
        ),
        title: 'Vẫn chưa kết nối được',
      ),
      duration: const Duration(seconds: 4),
    );
  }

  void _replace() {
    ref.read(addCameraProvider.notifier).startReplace(widget.detail.camera);
    context.push(AppRoutes.addCamera);
  }

  @override
  Widget build(BuildContext context) {
    final since = widget.detail.camera.signalLostSince;
    final names = widget.detail.notifiedNames;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      spacing: 12,
      children: [
        const CameraArtBox(
          art: MpIllustrations.camOffline,
          artSize: MpIllustration.figmaSize,
          height: 200,
        ),
        MpBanner(
          tone: MpBannerTone.warn,
          outlined: false,
          icon: MpIcons.wifiOff,
          title: since == null
              ? 'Mất tín hiệu'
              : 'Mất tín hiệu từ ${formatClock(since, seconds: false)}',
          body: [
            'Khu này đang không được canh cháy.',
            if (names.isNotEmpty) 'Đã báo ${names.join(', ')}.',
          ].join(' '),
        ),
        const MpTipsCard(
          tips: [
            (MpIcons.battery, 'Xem camera còn điện không'),
            (MpIcons.wifiOff, 'Xem mạng LAN tầng hầm'),
          ],
        ),
        const Spacer(),
        MpButton(
          label: 'Thử kết nối lại',
          onPressed: _busy ? null : _reconnect,
        ),
        if (_failures >= _replaceAfter && widget.detail.group.myRole.canManage)
          MpButton(
            label: 'Thêm lại RTSP',
            kind: MpButtonKind.ghost,
            onPressed: _busy ? null : _replace,
          ),
      ],
    );
  }
}
