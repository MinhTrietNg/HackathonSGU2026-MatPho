library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_page.dart';
import '../../core/widgets/mp_section_label.dart';
import '../../data/errors.dart';
import '../groups/group_widgets.dart' show showGroupFailureToast;
import 'camera_routes.dart';
import 'camera_state.dart';

const rtspPlaceholder = 'rtsp://192.168.1.10:554/stream1';

class AddCameraScreen extends ConsumerStatefulWidget {
  const AddCameraScreen({super.key, this.previewFocused = false});

  final bool previewFocused;

  @override
  ConsumerState<AddCameraScreen> createState() => _AddCameraScreenState();
}

class _AddCameraScreenState extends ConsumerState<AddCameraScreen> {
  late final _url = TextEditingController(
    text: ref.read(addCameraProvider).rtspUrl,
  );
  final _focus = FocusNode();

  @override
  void initState() {
    super.initState();
    _focus.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _url.dispose();
    _focus.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    final url = _url.text.trim();
    if (url.isEmpty) {
      _focus.requestFocus();
      return;
    }
    _focus.unfocus();
    final CameraConnectException? error;
    try {
      error = await ref.read(addCameraProvider.notifier).connect(url);
    } on MpException catch (e) {
      if (mounted) showGroupFailureToast(context, e);
      return;
    }
    if (!mounted) return;
    context.push(error == null ? CameraRoutes.name : CameraRoutes.connectError);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final busy = ref.watch(addCameraProvider.select((s) => s.busy));
    final secondary = t.caption.copyWith(
      fontWeight: FontWeight.w500,
      color: c.textSecondary,
    );
    final mono = t.mono.copyWith(fontSize: 11, color: c.textSecondary);
    return MpPage(
      header: MpHeader.back(
        title: 'Thêm camera RTSP',
        onBack: () => context.pop(),
      ),
      headerBottom: 12,
      gap: 12,
      children: [
        _RtspField(
          controller: _url,
          focusNode: _focus,
          focused: widget.previewFocused || _focus.hasFocus,
          onSubmitted: (_) => _connect(),
        ),
        Text.rich(
          TextSpan(
            children: [
              TextSpan(text: 'Dạng: ', style: secondary),
              TextSpan(
                text: 'rtsp://tài-khoản:mật-khẩu@IP:554/luồng',
                style: mono,
              ),
            ],
          ),
        ),
        const Padding(
          padding: EdgeInsets.only(top: 8),
          child: MpSectionLabel('CÁCH KẾT NỐI'),
        ),
        _Steps(secondary: secondary, mono: mono),
        const Spacer(),
        MpButton(label: 'Kết nối', onPressed: busy ? null : _connect),
      ],
    );
  }
}

class _RtspField extends StatelessWidget {
  const _RtspField({
    required this.controller,
    required this.focusNode,
    required this.focused,
    required this.onSubmitted,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final bool focused;
  final ValueChanged<String> onSubmitted;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final value = t.mono.copyWith(
      fontSize: 13,
      height: 1.5,
      color: c.textPrimary,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      spacing: 6,
      children: [
        Text('Đường dẫn RTSP', style: t.label.copyWith(color: c.textSecondary)),
        Container(
          height: 52,
          padding: const EdgeInsets.symmetric(horizontal: 14),
          decoration: BoxDecoration(
            color: c.bgCard,
            borderRadius: BorderRadius.circular(14),
            border: focused
                ? Border.all(color: c.brandAccent, width: 1.5)
                : Border.all(color: c.lineSubtle),
          ),
          child: Row(
            spacing: 10,
            children: [
              MpDuotoneIcon(
                MpIcons.camera,
                outline: c.textMuted,
                accent: c.textMuted,
                size: 20,
              ),
              Expanded(
                child: Semantics(
                  label: 'Đường dẫn RTSP',
                  child: TextField(
                    controller: controller,
                    focusNode: focusNode,
                    keyboardType: TextInputType.url,
                    autocorrect: false,
                    textInputAction: TextInputAction.go,
                    onSubmitted: onSubmitted,
                    style: value,
                    cursorColor: c.brandAccent,
                    decoration: InputDecoration.collapsed(
                      hintText: rtspPlaceholder,
                      hintStyle: value.copyWith(color: c.textMuted),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _Steps extends StatelessWidget {
  const _Steps({required this.secondary, required this.mono});

  final TextStyle secondary;
  final TextStyle mono;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final steps = <(String, InlineSpan)>[
      (
        'Bật RTSP trên camera',
        const TextSpan(
          text:
              'Mở app của hãng (Imou, Hikvision, Ezviz…) › Cài đặt › Mạng '
              '› bật RTSP.',
        ),
      ),
      (
        'Lấy địa chỉ IP của camera',
        const TextSpan(
          text:
              'Xem trong app hoặc trang quản trị router. Cổng RTSP mặc định '
              'là 554.',
        ),
      ),
      (
        'Chuẩn bị tài khoản camera',
        const TextSpan(
          text:
              'Tên đăng nhập và mật khẩu của camera. Chưa có thì hỏi bộ phận '
              'IT.',
        ),
      ),
      (
        'Ghép đường dẫn luồng',
        TextSpan(
          children: [
            const TextSpan(
              text: 'Thêm đuôi luồng của hãng, ví dụ Hikvision: \u200B',
            ),
            TextSpan(text: '/Streaming/Channels/102', style: mono),
            const TextSpan(text: '.'),
          ],
        ),
      ),
      (
        'Dán vào ô trên, ấn Kết nối',
        const TextSpan(
          text:
              'Mắt Phố thử mở luồng trong vài giây rồi cho bạn đặt tên '
              'camera.',
        ),
      ),
    ];
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 16),
      decoration: BoxDecoration(
        color: c.bgCard,
        border: Border.all(color: c.lineSubtle),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: 14,
        children: [
          for (final (i, (title, detail)) in steps.indexed)
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              spacing: 12,
              children: [
                Container(
                  width: 24,
                  height: 24,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: c.brandAccentSoft,
                    shape: BoxShape.circle,
                  ),
                  child: Text(
                    '${i + 1}',
                    style: context.mpText.mono.copyWith(
                      fontWeight: FontWeight.w600,
                      height: 1,
                      color: c.brandAccent,
                    ),
                  ),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    spacing: 2,
                    children: [
                      Text(
                        title,
                        style: context.mpText.body.copyWith(
                          fontWeight: FontWeight.w700,
                          height: 1.4,
                          color: c.textPrimary,
                        ),
                      ),
                      Text.rich(detail, style: secondary),
                    ],
                  ),
                ),
              ],
            ),
        ],
      ),
    );
  }
}
