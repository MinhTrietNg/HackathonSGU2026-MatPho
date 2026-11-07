library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../core/widgets/mp_page.dart';
import '../../core/widgets/mp_tips_card.dart';
import '../../data/errors.dart';
import '../groups/group_widgets.dart' show showGroupFailureToast;
import 'camera_routes.dart';
import 'camera_state.dart';

class ConnectErrorScreen extends ConsumerWidget {
  const ConnectErrorScreen({super.key});

  static const _artSize = Size(250, 250 * 180 / 280);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.mpColors;
    final t = context.mpText;
    final state = ref.watch(addCameraProvider);
    return MpPage(
      header: MpHeader.back(
        title: state.error?.cameraName ?? '',
        onBack: () => context.pop(),
      ),
      headerBottom: 14,
      gap: 14,
      children: [
        const Spacer(),
        const Center(
          child: MpIllustration(MpIllustrations.camOffline, size: _artSize),
        ),
        Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: 6,
          children: [
            Text(
              'Không kết nối được',
              textAlign: TextAlign.center,
              style: t.title.copyWith(
                fontWeight: FontWeight.w800,
                color: c.textPrimary,
              ),
            ),
            Text(
              'Camera không phản hồi.',
              textAlign: TextAlign.center,
              style: t.body.copyWith(
                fontWeight: FontWeight.w500,
                color: c.textSecondary,
              ),
            ),
          ],
        ),
        const MpTipsCard(
          tips: [
            (MpIcons.lock, 'Xem lại mật khẩu'),
            (MpIcons.wifiOff, 'Điện thoại phải dùng Wi-Fi công ty'),
            (MpIcons.settings, 'Nhờ IT cấp quyền cho camera'),
          ],
        ),
        const Spacer(),
        MpButton(
          label: 'Thử lại',
          onPressed: state.busy
              ? null
              : () async {
                  final CameraConnectException? error;
                  try {
                    error = await ref
                        .read(addCameraProvider.notifier)
                        .connect(state.rtspUrl);
                  } on MpException catch (e) {
                    if (context.mounted) showGroupFailureToast(context, e);
                    return;
                  }
                  if (error == null && context.mounted) {
                    context.pushReplacement(CameraRoutes.name);
                  }
                },
        ),
      ],
    );
  }
}
