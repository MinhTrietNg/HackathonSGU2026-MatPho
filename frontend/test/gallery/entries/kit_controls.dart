import 'package:flutter/material.dart';

import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_area_picker.dart';
import 'package:mat_pho/core/widgets/mp_badge.dart';
import 'package:mat_pho/core/widgets/mp_button.dart';
import 'package:mat_pho/core/widgets/mp_chip.dart';
import 'package:mat_pho/core/widgets/mp_duotone_icon.dart';
import 'package:mat_pho/core/widgets/mp_eye.dart';
import 'package:mat_pho/core/widgets/mp_header.dart';
import 'package:mat_pho/core/widgets/mp_icon_button.dart';
import 'package:mat_pho/core/widgets/mp_illustration.dart';
import 'package:mat_pho/core/widgets/mp_info_card.dart';
import 'package:mat_pho/core/widgets/mp_list_card.dart';
import 'package:mat_pho/core/widgets/mp_login_form.dart';
import 'package:mat_pho/core/widgets/mp_section_label.dart';
import 'package:mat_pho/core/widgets/mp_settings_row.dart';
import 'package:mat_pho/core/widgets/mp_stepper.dart';
import 'package:mat_pho/core/widgets/mp_text_field.dart';
import 'package:mat_pho/core/widgets/mp_toggle.dart';
import '../gallery_registry.dart';

typedef KitBoard = ({
  String code,
  String title,
  Size size,
  WidgetBuilder builder,
});

final kitControlBoards = <KitBoard>[
  (
    code: 'BTN',
    title: 'mp/Button · Kind × Size × State',
    size: const Size(2350, 826),
    builder: (_) => const _ButtonBoard(),
  ),
  (
    code: 'BTN2',
    title: 'mp/Button · icon, F2 actions, disabled · MpIconButton',
    size: const Size(318, 368),
    builder: (_) => const _ButtonExtrasBoard(),
  ),
  (
    code: 'HDR',
    title: 'mp/Header · Type=Back · Title',
    size: const Size(318, 157),
    builder: (_) => const _HeaderBoard(),
  ),
  (
    code: 'TGL',
    title: 'mp/toggle · On · Off',
    size: const Size(136, 58),
    builder: (_) => const _ToggleBoard(),
  ),
  (
    code: 'STP',
    title: 'mp/Stepper · step=1 · 2 · 3',
    size: const Size(668, 68),
    builder: (_) => const _StepperBoard(),
  ),
  (
    code: 'FLD',
    title: 'mp/Login · Form · Focus=none · phone · password',
    size: const Size(1082, 415),
    builder: (_) => const _LoginFormBoard(),
  ),
  (
    code: 'FLD2',
    title: 'MpTextField · lỗi (A6)',
    size: const Size(318, 189),
    builder: (_) => const _FieldErrorBoard(),
  ),
  (
    code: 'AREA',
    title: 'mp/Area picker · Selected=Hầm B1 · Hầm B2 · Sảnh tầng 1',
    size: const Size(366, 330),
    builder: (_) => const _AreaPickerBoard(),
  ),
  (
    code: 'EYE',
    title: 'mp/Eye · Look=idle · left · right · blink · down · closed',
    size: const Size(888, 112),
    builder: (_) => const _EyeBoard(),
  ),
  (
    code: 'CHIP',
    title: 'MpChip · lọc (G1) · gợi ý tên (D3)',
    size: const Size(318, 129),
    builder: (_) => const _ChipBoard(),
  ),
  (
    code: 'BADGE',
    title: 'MpBadge · cháy · không cháy · chưa chắc · báo nhầm · RTSP',
    size: const Size(318, 56),
    builder: (_) => const _BadgeBoard(),
  ),
  (
    code: 'ROW',
    title: 'MpSettingsRow · MpSettingsGroup · MpSectionLabel (H1)',
    size: const Size(318, 529),
    builder: (_) => const _SettingsBoard(),
  ),
  (
    code: 'CARD',
    title: 'MpListCard (G1 · K1)',
    size: const Size(318, 776),
    builder: (_) => const _ListCardBoard(),
  ),
  (
    code: 'INFO',
    title: 'MpInfoCard (F2)',
    size: const Size(318, 133),
    builder: (_) => const _InfoCardBoard(),
  ),
];

final kitControlsEntries = <GalleryEntry>[
  for (final board in kitControlBoards)
    GalleryEntry(
      code: board.code,
      title: board.title,
      builder: (context) =>
          _BoardPreview(size: board.size, child: board.builder(context)),
    ),
];

void _noop() {}

class _BoardPreview extends StatelessWidget {
  const _BoardPreview({required this.size, required this.child});

  final Size size;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: SizedBox.fromSize(size: size, child: child),
          ),
        ),
      ),
    );
  }
}

class _Board extends StatelessWidget {
  const _Board({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: context.mpColors.bgBase,
      child: Stack(children: children),
    );
  }
}

class _Column extends StatelessWidget {
  const _Column({required this.spacing, required this.children});

  final double spacing;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: context.mpColors.bgBase,
      child: Align(
        alignment: Alignment.topLeft,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: spacing,
          children: children,
        ),
      ),
    );
  }
}

class _ButtonBoard extends StatelessWidget {
  const _ButtonBoard();

  static const _p = MpButtonKind.primary;
  static const _s = MpButtonKind.secondary;
  static const _g = MpButtonKind.ghost;
  static const _q = MpButtonKind.quiet;
  static const _d = MpButtonKind.danger;
  static const _a = MpButtonKind.amber;
  static const _m = MpButtonSize.m;
  static const _l = MpButtonSize.l;
  static const _xl = MpButtonSize.xl;

  static const _variants = [
    (24.0, 24.0, _p, _l, false),
    (366.0, 24.0, _p, _m, false),
    (708.0, 24.0, _s, _l, false),
    (1050.0, 24.0, _s, _m, false),
    (1392.0, 24.0, _g, _l, false),
    (1734.0, 24.0, _g, _m, false),
    (24.0, 100.0, _q, _l, false),
    (366.0, 100.0, _q, _m, false),
    (708.0, 100.0, _d, _l, false),
    (1050.0, 100.0, _d, _m, false),
    (1392.0, 100.0, _d, _xl, false),
    (1734.0, 100.0, _a, _l, false),
    (24.0, 184.0, _a, _m, false),
    (366.0, 184.0, _s, _xl, false),
    (708.0, 184.0, _a, _xl, false),
    (1050.0, 184.0, _p, _l, true),
    (1392.0, 184.0, _p, _m, true),
    (1734.0, 184.0, _s, _l, true),
    (24.0, 268.0, _s, _m, true),
    (366.0, 268.0, _g, _l, true),
    (708.0, 268.0, _g, _m, true),
    (1050.0, 268.0, _q, _l, true),
    (1392.0, 268.0, _q, _m, true),
    (1734.0, 268.0, _d, _l, true),
    (24.0, 344.0, _d, _m, true),
    (366.0, 344.0, _d, _xl, true),
    (708.0, 344.0, _a, _l, true),
    (1050.0, 344.0, _a, _m, true),
    (1392.0, 344.0, _s, _xl, true),
    (1734.0, 344.0, _a, _xl, true),
  ];

  @override
  Widget build(BuildContext context) {
    return _Board(
      children: [
        for (final (x, y, kind, size, pressed) in _variants)
          Positioned(
            left: x,
            top: y,
            width: 318,
            child: MpButton(
              label: 'Nút',
              kind: kind,
              size: size,
              pressed: pressed,
              onPressed: _noop,
            ),
          ),
      ],
    );
  }
}

class _ButtonExtrasBoard extends StatelessWidget {
  const _ButtonExtrasBoard();

  @override
  Widget build(BuildContext context) {
    return _Column(
      spacing: 12,
      children: [
        const MpButton(
          label: 'Gọi 114',
          kind: MpButtonKind.danger,
          size: MpButtonSize.xl,
          icon: MpIcons.call,
          onPressed: _noop,
        ),
        const Row(
          spacing: 12,
          children: [
            Expanded(
              child: MpButton(
                label: 'Báo nhầm',
                kind: MpButtonKind.report,
                icon: MpIcons.flag,
                onPressed: _noop,
              ),
            ),
            Expanded(
              child: MpButton(
                label: 'Đã xử lý',
                kind: MpButtonKind.resolve,
                icon: MpIcons.check,
                onPressed: _noop,
              ),
            ),
          ],
        ),
        const MpButton(
          label: 'Tải lên',
          icon: MpIcons.upload,
          onPressed: _noop,
        ),
        const MpButton(
          label: 'Gửi mã OTP',
          icon: MpIcons.sms,
          onPressed: _noop,
        ),
        const Row(
          spacing: 12,
          children: [
            Expanded(child: MpButton(label: 'Nút', onPressed: null)),
            Expanded(
              child: MpButton(
                label: 'Nút',
                kind: MpButtonKind.secondary,
                onPressed: null,
              ),
            ),
          ],
        ),
        Row(
          spacing: 12,
          children: [
            const MpIconButton(
              icon: MpIcons.back,
              semanticLabel: 'Quay lại',
              onPressed: _noop,
            ),
            const MpIconButton(
              icon: MpIcons.flag,
              semanticLabel: 'Báo cáo',
              onPressed: _noop,
            ),
            const MpIconButton(
              icon: MpIcons.plus,
              semanticLabel: 'Thêm',
              accent: true,
              onPressed: _noop,
            ),
            MpIconButton(
              icon: MpIcons.plus,
              semanticLabel: 'Thêm',
              iconAccent: context.mpColors.brandAccent,
              onPressed: _noop,
            ),
          ],
        ),
      ],
    );
  }
}

class _HeaderBoard extends StatelessWidget {
  const _HeaderBoard();

  @override
  Widget build(BuildContext context) {
    return const _Board(
      children: [
        Positioned(
          left: 24,
          top: 24,
          width: 270,
          child: MpHeader.back(title: 'Tiêu đề', onBack: _noop),
        ),
        Positioned(
          left: 24,
          top: 96,
          width: 270,
          child: MpHeader.title(title: 'Tiêu đề'),
        ),
      ],
    );
  }
}

class _ToggleBoard extends StatelessWidget {
  const _ToggleBoard();

  @override
  Widget build(BuildContext context) {
    return _Board(
      children: [
        Positioned(
          left: 16,
          top: 16,
          child: MpToggle(value: true, onChanged: (_) {}),
        ),
        Positioned(
          left: 76,
          top: 16,
          child: MpToggle(value: false, onChanged: (_) {}),
        ),
      ],
    );
  }
}

class _StepperBoard extends StatelessWidget {
  const _StepperBoard();

  @override
  Widget build(BuildContext context) {
    return const _Board(
      children: [
        Positioned(left: 16, top: 16, child: MpStepper(current: 1)),
        Positioned(left: 236, top: 16, child: MpStepper(current: 2)),
        Positioned(left: 456, top: 16, child: MpStepper(current: 3)),
      ],
    );
  }
}

class _LoginFormBoard extends StatelessWidget {
  const _LoginFormBoard();

  @override
  Widget build(BuildContext context) {
    return _Board(
      children: [
        for (final (i, focus) in MpLoginFocus.values.indexed)
          Positioned(
            left: 24 + 358.0 * i,
            top: 24,
            width: 318,
            child: _FilledLoginForm(focus: focus),
          ),
      ],
    );
  }
}

class _FilledLoginForm extends StatefulWidget {
  const _FilledLoginForm({required this.focus});

  final MpLoginFocus focus;

  @override
  State<_FilledLoginForm> createState() => _FilledLoginFormState();
}

class _FilledLoginFormState extends State<_FilledLoginForm> {
  final _phone = TextEditingController(text: '0912 345 678');
  final _password = TextEditingController(text: 'matpho2025');

  @override
  void dispose() {
    _phone.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MpLoginForm(
      phoneController: _phone,
      passwordController: _password,
      focus: widget.focus,
      idleLoop: false,
      onForgotPassword: _noop,
    );
  }
}

class _FieldErrorBoard extends StatefulWidget {
  const _FieldErrorBoard();

  @override
  State<_FieldErrorBoard> createState() => _FieldErrorBoardState();
}

class _FieldErrorBoardState extends State<_FieldErrorBoard> {
  final _phone = TextEditingController(text: '0912 345 678');
  final _password = TextEditingController(text: 'matpho');

  @override
  void dispose() {
    _phone.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return _Column(
      spacing: 16,
      children: [
        MpTextField(
          label: 'Số điện thoại',
          icon: MpIcons.phone,
          controller: _phone,
        ),
        MpTextField(
          label: 'Mật khẩu',
          icon: MpIcons.lock,
          controller: _password,
          obscure: true,
          errorText: 'Mật khẩu không đúng',
        ),
      ],
    );
  }
}

class _AreaPickerBoard extends StatelessWidget {
  const _AreaPickerBoard();

  static const _areas = ['Hầm B1', 'Hầm B2', 'Sảnh tầng 1'];

  @override
  Widget build(BuildContext context) {
    return _Board(
      children: [
        for (final (i, selected) in _areas.indexed)
          Positioned(
            left: 24,
            top: 24 + 102.0 * i,
            width: 318,
            child: MpAreaPicker(
              areas: _areas,
              selected: selected,
              onSelected: (_) {},
              onAdd: _noop,
            ),
          ),
      ],
    );
  }
}

class _EyeBoard extends StatelessWidget {
  const _EyeBoard();

  @override
  Widget build(BuildContext context) {
    return _Board(
      children: [
        for (final (i, look) in MpEyeLook.values.indexed)
          Positioned(
            left: 24 + 144.0 * i,
            top: 24,
            child: MpEye(look: look, idleLoop: false),
          ),
      ],
    );
  }
}

class _ChipBoard extends StatelessWidget {
  const _ChipBoard();

  @override
  Widget build(BuildContext context) {
    return _Column(
      spacing: 16,
      children: [
        Row(
          spacing: 6,
          children: [
            for (final (i, label) in const [
              'Tất cả',
              'Cháy',
              'Không cháy',
              'Báo nhầm',
            ].indexed)
              MpChip(
                label: label,
                style: MpChipStyle.filled,
                selected: i == 0,
                onTap: _noop,
              ),
          ],
        ),
        Wrap(
          spacing: 8,
          runSpacing: 12,
          children: [
            for (final (i, label) in const [
              'Hầm xe',
              'Tầng trệt',
              'Cửa hàng',
              'Kho',
            ].indexed)
              MpChip(
                label: label,
                style: MpChipStyle.suggestion,
                selected: i == 0,
                onTap: _noop,
              ),
          ],
        ),
      ],
    );
  }
}

class _BadgeBoard extends StatelessWidget {
  const _BadgeBoard();

  @override
  Widget build(BuildContext context) {
    return const _Column(
      spacing: 0,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            MpBadge(label: 'Cháy', tone: MpBadgeTone.fire),
            MpBadge(label: 'Không cháy', tone: MpBadgeTone.ok),
            MpBadge(label: 'Chưa chắc chắn', tone: MpBadgeTone.warn),
            MpBadge(label: 'Báo nhầm', tone: MpBadgeTone.neutral),
            MpBadge(label: 'Đã xác nhận cháy', tone: MpBadgeTone.fire),
            MpBadge(label: 'RTSP', tone: MpBadgeTone.accent, dot: false),
          ],
        ),
      ],
    );
  }
}

class _SettingsBoard extends StatelessWidget {
  const _SettingsBoard();

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return _Column(
      spacing: 10,
      children: [
        const MpSectionLabel('CẢNH BÁO'),
        MpSettingsGroup(
          children: [
            MpSettingsRow(
              icon: MpIcons.bell,
              iconColor: c.brandAccent,
              title: 'Thử báo cháy',
              subtitle: 'Xem máy có kêu không',
              onTap: _noop,
            ),
            MpSettingsRow(
              icon: MpIcons.sound,
              iconColor: c.brandAccent,
              title: 'Kêu cả khi im lặng',
              trailing: MpToggle(value: true, onChanged: (_) {}),
            ),
          ],
        ),
        const MpSectionLabel('GIAO DIỆN'),
        MpSettingsGroup(
          children: [
            MpSettingsRow(
              icon: MpIcons.sun,
              iconColor: c.brandAccent,
              title: 'Giao diện sáng',
              trailing: MpToggle(value: false, onChanged: (_) {}),
            ),
          ],
        ),
        const MpSectionLabel('TÀI KHOẢN'),
        MpSettingsGroup(
          children: [
            MpSettingsRow(
              icon: MpIcons.film,
              iconColor: c.textSecondary,
              title: 'Camera',
              value: '3',
              onTap: _noop,
            ),
            MpSettingsRow(
              icon: MpIcons.user,
              iconColor: c.brandAccent,
              title: 'Nhóm & thành viên',
              value: '4',
              onTap: _noop,
            ),
            MpSettingsRow(
              icon: MpIcons.key,
              iconColor: c.textSecondary,
              title: 'Đổi mật khẩu',
              onTap: _noop,
            ),
            MpSettingsRow(
              icon: MpIcons.shield,
              iconColor: c.textSecondary,
              title: 'Quyền riêng tư',
              onTap: _noop,
            ),
          ],
        ),
      ],
    );
  }
}

class _ListCardBoard extends StatelessWidget {
  const _ListCardBoard();

  static const _thumb = Size(75, 48.214);

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    Widget icon(String asset) => MpDuotoneIcon(
      asset,
      outline: c.textMuted,
      accent: c.textMuted,
      size: 18,
    );
    Widget feed(String asset) => MpIllustration(asset, size: _thumb);
    return _Column(
      spacing: 10,
      children: [
        MpListCard(
          thumbnail: feed(MpIllustrations.feedFire),
          title: 'Lửa ở xe máy',
          subtitle: 'Hầm xe · 21:47 · đã gọi 114',
          badge: const MpBadge(label: 'Cháy', tone: MpBadgeTone.fire),
          trailing: icon(MpIcons.chevron),
          onTap: _noop,
        ),
        MpListCard(
          thumbnail: feed(MpIllustrations.feed),
          title: 'Đèn xe chiếu lên tường',
          subtitle: 'Hầm xe · 21:40',
          badge: const MpBadge(label: 'Không cháy', tone: MpBadgeTone.ok),
          trailing: icon(MpIcons.chevron),
          onTap: _noop,
        ),
        MpListCard(
          thumbnail: feed(MpIllustrations.feedSmoke),
          title: 'Khói mờ ở lối xuống',
          subtitle: 'Hầm xe · 19:02',
          badge: const MpBadge(label: 'Chưa chắc chắn', tone: MpBadgeTone.warn),
          trailing: icon(MpIcons.chevron),
          onTap: _noop,
        ),
        MpListCard(
          thumbnail: feed(MpIllustrations.feedSmoke),
          title: 'Hơi nước từ ống xả',
          subtitle: 'Hầm xe · 08:15',
          badge: const MpBadge(label: 'Báo nhầm', tone: MpBadgeTone.neutral),
          trailing: icon(MpIcons.chevron),
          onTap: _noop,
        ),
        MpListCard(
          thumbnail: feed(MpIllustrations.feedSmoke),
          title: 'Cháy xe máy · Hầm B1',
          subtitle: 'hamxe_chay.mp4 · 0:45',
          trailing: icon(MpIcons.play),
          onTap: _noop,
        ),
        MpListCard(
          thumbnail: feed(MpIllustrations.feed),
          title: 'Hầm xe bình thường',
          subtitle: 'hamxe_binhthuong.mp4 · 0:40',
          trailing: icon(MpIcons.play),
          onTap: _noop,
        ),
        MpListCard(
          dashed: true,
          thumbnail: MpDuotoneIcon(
            MpIcons.upload,
            outline: c.textPrimary,
            accent: c.brandAccent,
          ),
          title: 'Tải video lên',
          subtitle: 'MP4 · tối đa 200 MB · AI quét ngay',
          onTap: _noop,
        ),
        MpListCard(
          dimmed: true,
          thumbnail: feed(MpIllustrations.feed),
          title: 'Kết nối camera hầm xe',
          subtitle: 'Dán đường dẫn RTSP, AI quét 24/7',
          badge: const MpBadge(
            label: 'RTSP',
            tone: MpBadgeTone.accent,
            dot: false,
          ),
          trailing: icon(MpIcons.chevron),
          onTap: _noop,
        ),
      ],
    );
  }
}

class _InfoCardBoard extends StatelessWidget {
  const _InfoCardBoard();

  @override
  Widget build(BuildContext context) {
    return _Column(
      spacing: 0,
      children: [
        MpInfoCard(
          rows: [
            (label: 'Lúc', value: '21:47:31 · 12 giây trước', valueColor: null),
            (
              label: 'Độ chắc chắn',
              value: '93% · đã kiểm tra 2 lần',
              valueColor: context.mpColors.statusFire,
            ),
            (
              label: 'Thấy gì',
              value: 'Lửa và khói ở xe máy bên trái',
              valueColor: null,
            ),
          ],
        ),
      ],
    );
  }
}
