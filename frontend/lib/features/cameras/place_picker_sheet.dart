library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_sheet.dart';
import '../groups/current_group.dart';
import '../groups/group_state.dart' show groupDisplayName, roleLabel;
import 'camera_state.dart';
import 'camera_widgets.dart';

Future<void> showPlacePicker(BuildContext context) {
  final container = ProviderScope.containerOf(context, listen: false);
  return showMpSheet<void>(
    context,
    builder: (_) => UncontrolledProviderScope(
      container: container,
      child: const PlacePickerSheet(),
    ),
  );
}

class PlacePickerSheet extends ConsumerWidget {
  const PlacePickerSheet({super.key});

  static const _icons = [MpIcons.shield, MpIcons.user, MpIcons.camera];

  static String _iconOf(CameraPlace place, List<CameraPlace> places) {
    if (place.group.isPersonal) return MpIcons.camera;
    final shared = places.where((p) => !p.group.isPersonal).toList();
    return _icons[shared.indexOf(place) % _icons.length];
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.mpColors;
    final places = ref.watch(cameraPlacesProvider).value ?? const [];
    final current = ref.watch(currentPlaceProvider).value;
    return CameraSheet(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
      spacing: 10,
      handleColor: c.lineSubtle,
      centerHandle: false,
      children: [
        Semantics(
          header: true,
          child: Text(
            'Chọn nơi',
            style: context.mpText.title.copyWith(
              fontSize: 18,
              fontWeight: FontWeight.w800,
              height: normalHeight(18),
              color: c.textPrimary,
            ),
          ),
        ),
        for (final place in places)
          _PlaceRow(
            icon: _iconOf(place, places),
            name: groupDisplayName(place.group),
            detail:
                '${place.cameraCount} camera · '
                '${roleLabel(place.group.myRole)}',
            selected: place.group.id == current?.id,
            onTap: () {
              ref.read(currentGroupIdProvider.notifier).select(place.group.id);
              Navigator.of(context).pop();
            },
          ),
      ],
    );
  }
}

class _PlaceRow extends StatelessWidget {
  const _PlaceRow({
    required this.icon,
    required this.name,
    required this.detail,
    required this.selected,
    required this.onTap,
  });

  final String icon;
  final String name;
  final String detail;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return Semantics(
      button: true,
      selected: selected,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: selected ? c.brandAccentSoft : c.bgCard,
            borderRadius: BorderRadius.circular(16),
            border: selected
                ? Border.all(color: c.brandAccent, width: 1.5)
                : null,
          ),
          child: Row(
            spacing: 12,
            children: [
              Container(
                width: 40,
                height: 40,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: c.bgRaised,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: MpScaledIcon(
                  icon,
                  color: selected ? c.brandAccentFg : c.textSecondary,
                  size: 20,
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  spacing: 2,
                  children: [
                    Text(
                      name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: t.body.copyWith(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        height: normalHeight(15),
                        color: c.textPrimary,
                      ),
                    ),
                    Text(
                      detail,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: t.caption.copyWith(
                        fontWeight: FontWeight.w500,
                        height: normalHeight(12),
                        color: c.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              if (selected)
                MpScaledIcon(MpIcons.check, color: c.brandAccentFg, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}
