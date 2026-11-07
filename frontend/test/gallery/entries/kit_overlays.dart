import 'package:flutter/material.dart';

import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_banner.dart';
import 'package:mat_pho/core/widgets/mp_dialog.dart';
import 'package:mat_pho/core/widgets/mp_duotone_icon.dart';
import 'package:mat_pho/core/widgets/mp_illustration.dart';
import 'package:mat_pho/core/widgets/mp_sheet.dart';
import 'package:mat_pho/core/widgets/mp_tab_bar.dart';
import 'package:mat_pho/core/widgets/mp_toast.dart';
import '../gallery_registry.dart';

typedef KitOverlayDemo = ({
  String code,
  String title,
  int? tab,
  void Function(BuildContext context, {required bool replay}) show,
});

typedef KitBannerBoard = ({
  String code,
  String title,
  Size size,
  WidgetBuilder builder,
});

final kitOverlayDemos = <KitOverlayDemo>[
  (
    code: 'SHEET',
    title: 'mp/Sheet · State=open (Kết thúc sự cố, rows/button = placeholder)',
    tab: null,
    show: (context, {required replay}) => showMpSheet<void>(
      context,
      builder: (_) => const MpSheet(
        title: 'Kết quả thế nào?',
        subtitle: 'Giúp lịch sử chính xác và AI học tốt hơn.',
        spacing: 12,
        children: [
          _Placeholder(height: 67, label: 'row · Cháy thật, đã xử lý'),
          _Placeholder(height: 64, label: 'row · Đã kiểm tra, không có cháy'),
          _Placeholder(height: 64, label: 'row · Báo nhầm'),
          _Placeholder(height: 52, label: 'btn · Lưu vào lịch sử'),
        ],
      ),
    ),
  ),
  (
    code: 'DLG',
    title: 'mp/Dialog · State=open (Xoá nguồn, buttons = placeholder)',
    tab: null,
    show: (context, {required replay}) => showMpDialog<void>(
      context,
      builder: (_) => const MpDialog(
        illustration: MpIllustration(
          MpIllustrations.delete,
          size: MpDialog.illustrationSize,
        ),
        title: 'Xoá "Hầm xe"?',
        body: 'Sẽ ngừng canh cháy ở đây. Lịch sử giữ 30 ngày.',
        actions: [
          _Placeholder(height: 52, label: 'btn · Xoá'),
          _Placeholder(height: 46, label: 'btn · Huỷ'),
        ],
      ),
    ),
  ),
  (
    code: 'TOAST-UNDO',
    title: 'Toast · Đã báo nhầm · Hoàn tác 5 s (K5, I10)',
    tab: 0,
    show: (context, {required replay}) {
      final c = context.mpColors;
      showMpToast(
        context,
        MpToast(
          icon: MpDuotoneIcon(
            MpIcons.flag,
            outline: c.textPrimary,
            accent: c.textPrimary,
            size: 18,
          ),
          title: 'Đã báo nhầm · Hầm xe',
          actionLabel: 'Hoàn tác',
          onAction: () {},
        ),
        duration: replay ? MpToast.undoDuration : null,
      );
    },
  ),
  (
    code: 'TOAST-DONE',
    title: 'Toast · Đã xử lý · Hoàn tác (K4)',
    tab: 0,
    show: (context, {required replay}) {
      final c = context.mpColors;
      showMpToast(
        context,
        MpToast(
          icon: MpDuotoneIcon(
            MpIcons.check,
            outline: c.statusOk,
            accent: c.statusOk,
            size: 18,
          ),
          title: 'Đã xử lý · Hầm xe',
          actionLabel: 'Hoàn tác',
          onAction: () {},
        ),
        duration: replay ? MpToast.undoDuration : null,
      );
    },
  ),
  (
    code: 'TOAST-DISMISS',
    title: 'Toast · Không phải cháy · 4 s (E4)',
    tab: 0,
    show: (context, {required replay}) => showMpToast(
      context,
      MpToast.rich(
        thumbnail: const MpIllustration(
          MpIllustrations.dismissed,
          size: MpToast.thumbnailArtSize,
        ),
        title: 'Không phải cháy',
        subtitle: 'Chỉ là đèn xe chiếu lên tường.',
        actionLabel: 'Xem',
        onAction: () {},
      ),
      bottom: MpTabBar.height + 20,
      duration: replay ? MpToast.dismissedDuration : null,
    ),
  ),
  (
    code: 'BNR-FIRE',
    title: 'Banner · Cháy · in-app, tab khác (F6)',
    tab: 1,
    show: (context, {required replay}) => showMpAlertBanner(
      context,
      MpAlertBanner(
        title: 'Cháy · Hầm xe',
        subtitle: 'Lửa ở xe máy · chạm để xem',
        onTap: () {},
      ),
    ),
  ),
];

final kitBannerBoards = <KitBannerBoard>[
  (
    code: 'BNR-ERROR',
    title: 'banner · Sai mật khẩu (A6) · tone fire, no outline',
    size: const Size(318, 66),
    builder: (_) => const MpBanner(
      tone: MpBannerTone.fire,
      icon: MpIcons.alert,
      title: 'Sai mật khẩu',
      body: 'Còn 3 lần thử. Sai tiếp sẽ khoá 15 phút.',
      outlined: false,
    ),
  ),
  (
    code: 'BNR-WARN',
    title: 'banner · Mất tín hiệu từ 21:30 (I8) · tone warn, no outline',
    size: const Size(318, 83),
    builder: (_) => const MpBanner(
      tone: MpBannerTone.warn,
      icon: MpIcons.wifiOff,
      title: 'Mất tín hiệu từ 21:30',
      body: 'Khu này đang không được canh cháy. Đã báo chị Lan.',
      outlined: false,
    ),
  ),
  (
    code: 'BNR-OFFLINE',
    title: 'banner · Mất kết nối mạng (E5) · tone warn + thumbnail',
    size: const Size(318, 78),
    builder: (_) => const MpBanner(
      tone: MpBannerTone.warn,
      thumbnail: MpIllustration(
        MpIllustrations.offline,
        size: MpBanner.thumbnailArtSize,
      ),
      title: 'Mất mạng',
      body: '1 ảnh đang chờ. Có mạng sẽ tự gửi.',
    ),
  ),
  (
    code: 'BNR-SLOW',
    title: 'banner · Máy đang nóng (E6) · tone accent + thumbnail',
    size: const Size(318, 83),
    builder: (_) => const MpBanner(
      tone: MpBannerTone.accent,
      thumbnail: MpIllustration(
        MpIllustrations.slowDevice,
        size: MpBanner.thumbnailArtSize,
      ),
      title: 'Máy nóng, đã quét chậm lại',
      body: 'Vẫn phát hiện được cháy, chậm hơn khoảng 1 giây.',
    ),
  ),
  (
    code: 'BNR-INFO',
    title: 'banner · Mật khẩu ở đâu? (I3) · tone accent, no outline',
    size: const Size(318, 66),
    builder: (_) => const MpBanner(
      tone: MpBannerTone.accent,
      icon: MpIcons.info,
      title: 'Chưa có mật khẩu?',
      body: 'Hỏi bộ phận IT của công ty.',
      outlined: false,
    ),
  ),
];

final kitOverlaysEntries = <GalleryEntry>[
  for (final demo in kitOverlayDemos)
    GalleryEntry(
      code: demo.code,
      title: demo.title,
      builder: (_) => _OverlayDemo(demo),
    ),
  for (final board in kitBannerBoards)
    GalleryEntry(
      code: board.code,
      title: board.title,
      builder: (context) => Scaffold(
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
            child: Align(
              alignment: Alignment.topCenter,
              child: board.builder(context),
            ),
          ),
        ),
      ),
    ),
];

class _OverlayDemo extends StatefulWidget {
  const _OverlayDemo(this.demo);

  final KitOverlayDemo demo;

  @override
  State<_OverlayDemo> createState() => _OverlayDemoState();
}

class _OverlayDemoState extends State<_OverlayDemo> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) widget.demo.show(context, replay: false);
    });
  }

  @override
  Widget build(BuildContext context) {
    final tab = widget.demo.tab;
    return PopScope(
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) return;
        hideMpToast();
        hideMpAlertBanner();
      },
      child: Scaffold(
        body: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => widget.demo.show(context, replay: true),
        ),
        bottomNavigationBar: tab == null
            ? null
            : MpTabBar(currentIndex: tab, onTap: (_) {}),
      ),
    );
  }
}

class _Placeholder extends StatelessWidget {
  const _Placeholder({required this.height, required this.label});

  final double height;
  final String label;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Container(
      height: height,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        border: Border.all(color: c.textMuted),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Text(
        'PLACEHOLDER · $label',
        style: context.mpText.mono.copyWith(color: c.textMuted),
      ),
    );
  }
}
