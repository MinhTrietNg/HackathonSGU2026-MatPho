import 'package:flutter/material.dart';

import 'mp_chip.dart';

class MpAreaPicker extends StatelessWidget {
  const MpAreaPicker({
    super.key,
    required this.areas,
    required this.selected,
    required this.onSelected,
    required this.onAdd,
  });

  final List<String> areas;

  final String? selected;
  final ValueChanged<String> onSelected;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final area in areas)
          MpChip(
            label: area,
            selected: area == selected,
            onTap: () => onSelected(area),
          ),
        MpChip(label: '+ Khu vực mới', style: MpChipStyle.add, onTap: onAdd),
      ],
    );
  }
}
