library;

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_toast.dart';
import '../../data/errors.dart';
import '../../data/models/fire_event.dart';
import '../../data/providers.dart';

void showResolvedToast(BuildContext context, {VoidCallback? onUndo}) =>
    _showForLatestEvent(
      context,
      (e) => e.resolved,
      (target, location) =>
          showResolvedToastFor(target, locationName: location, onUndo: onUndo),
    );

void showFalseAlarmToast(
  BuildContext context, {
  required VoidCallback onUndo,
}) => _showForLatestEvent(
  context,
  (e) => e.status == EventStatus.falseAlarm,
  (target, location) =>
      showFalseAlarmToastFor(target, locationName: location, onUndo: onUndo),
);

void showResolvedToastFor(
  BuildContext context, {
  required String? locationName,
  VoidCallback? onUndo,
  Duration? duration = MpToast.undoDuration,
}) {
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
      title: _withPlace('Đã xử lý', locationName),
      actionLabel: onUndo == null ? null : 'Hoàn tác',
      onAction: onUndo,
    ),
    duration: duration,
  );
}

void showFalseAlarmToastFor(
  BuildContext context, {
  required String? locationName,
  required VoidCallback onUndo,
  Duration? duration = MpToast.undoDuration,
}) {
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
      title: _withPlace('Đã báo nhầm', locationName),
      actionLabel: 'Hoàn tác',
      onAction: onUndo,
    ),
    duration: duration,
  );
}

String _withPlace(String action, String? place) =>
    place == null ? action : '$action · $place';

Future<void> _showForLatestEvent(
  BuildContext context,
  bool Function(FireEvent) test,
  void Function(BuildContext target, String? location) show,
) async {
  final overlay = Overlay.of(context, rootOverlay: true);
  final history = ProviderScope.containerOf(
    context,
    listen: false,
  ).read(historyRepositoryProvider);
  String? location;
  try {
    final events = await history.list();
    location = events.where(test).firstOrNull?.locationName;
  } on MpException {
    location = null;
  }
  if (!overlay.mounted) return;
  late final OverlayEntry anchor;
  var shown = false;
  anchor = OverlayEntry(
    builder: (target) {
      if (!shown) {
        shown = true;
        WidgetsBinding.instance.addPostFrameCallback((_) {
          show(target, location);
          anchor
            ..remove()
            ..dispose();
        });
      }
      return const SizedBox.shrink();
    },
  );
  overlay.insert(anchor);
}
