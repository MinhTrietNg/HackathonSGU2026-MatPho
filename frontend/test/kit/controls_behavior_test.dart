import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_area_picker.dart';
import 'package:mat_pho/core/widgets/mp_button.dart';
import 'package:mat_pho/core/widgets/mp_duotone_icon.dart';
import 'package:mat_pho/core/widgets/mp_eye.dart';
import 'package:mat_pho/core/widgets/mp_header.dart';
import 'package:mat_pho/core/widgets/mp_login_form.dart';
import 'package:mat_pho/core/widgets/mp_settings_row.dart';
import 'package:mat_pho/core/widgets/mp_text_field.dart';
import 'package:mat_pho/core/widgets/mp_toggle.dart';

Future<void> _pump(WidgetTester tester, Widget child) {
  return tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.dark(),
      home: Scaffold(
        body: Padding(padding: const EdgeInsets.all(20), child: child),
      ),
    ),
  );
}

void main() {
  testWidgets('MpButton taps, presses down onto its edge, and disables', (
    tester,
  ) async {
    var taps = 0;
    await _pump(
      tester,
      Column(
        children: [
          MpButton(label: 'Đăng nhập', onPressed: () => taps++),
          const MpButton(label: 'Tắt', onPressed: null),
        ],
      ),
    );

    double faceTop() => tester
        .widgetList<Positioned>(
          find.descendant(
            of: find.byType(MpButton).first,
            matching: find.byType(Positioned),
          ),
        )
        .last
        .top!;

    expect(faceTop(), 0);
    final gesture = await tester.startGesture(
      tester.getCenter(find.text('Đăng nhập')),
    );
    await tester.pump();
    expect(faceTop(), 4, reason: 'pressed face covers the 4px edge');
    await gesture.up();
    await tester.pump();
    expect(faceTop(), 0);
    expect(taps, 1);

    await tester.tap(find.text('Tắt'));
    expect(taps, 1);
    expect(
      tester.getSemantics(find.byType(MpButton).last),
      matchesSemantics(isButton: true, hasEnabledState: true, label: 'Tắt'),
    );
  });

  testWidgets('MpToggle reports the flipped value', (tester) async {
    bool? changed;
    await _pump(tester, MpToggle(value: false, onChanged: (v) => changed = v));
    await tester.tap(find.byType(MpToggle));
    expect(changed, isTrue);
  });

  testWidgets('MpTextField reveals the password and shows the error', (
    tester,
  ) async {
    await _pump(
      tester,
      MpTextField(
        label: 'Mật khẩu',
        icon: MpIcons.lock,
        controller: TextEditingController(text: 'matpho'),
        obscure: true,
        errorText: 'Mật khẩu không đúng',
      ),
    );
    bool obscured() =>
        tester.widget<TextField>(find.byType(TextField)).obscureText;

    expect(obscured(), isTrue);
    expect(find.text('Mật khẩu không đúng'), findsOneWidget);
    await tester.tap(find.text('Hiện'));
    await tester.pump();
    expect(obscured(), isFalse);
    expect(find.text('Ẩn'), findsOneWidget);
  });

  testWidgets('MpAreaPicker selects an area and opens "Khu vực mới"', (
    tester,
  ) async {
    String? selected;
    var added = false;
    await _pump(
      tester,
      MpAreaPicker(
        areas: const ['Hầm B1', 'Hầm B2'],
        selected: 'Hầm B1',
        onSelected: (a) => selected = a,
        onAdd: () => added = true,
      ),
    );
    await tester.tap(find.text('Hầm B2'));
    await tester.tap(find.text('+ Khu vực mới'));
    expect(selected, 'Hầm B2');
    expect(added, isTrue);
  });

  testWidgets('MpHeader and MpSettingsRow call back', (tester) async {
    var back = 0;
    var row = 0;
    await _pump(
      tester,
      Builder(
        builder: (context) => Column(
          children: [
            MpHeader.back(title: 'Thêm video', onBack: () => back++),
            MpSettingsRow(
              icon: MpIcons.key,
              iconColor: context.mpColors.textSecondary,
              title: 'Đổi mật khẩu',
              onTap: () => row++,
            ),
          ],
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('Quay lại'));
    await tester.tap(find.text('Đổi mật khẩu'));
    expect((back, row), (1, 1));
  });

  testWidgets('MpLoginForm points the eye at the focused field', (
    tester,
  ) async {
    await _pump(tester, const SingleChildScrollView(child: MpLoginForm()));
    MpEyeLook look() => tester.widget<MpEye>(find.byType(MpEye)).look;

    expect(look(), MpEyeLook.idle);
    await tester.tap(find.byType(TextField).first);
    await tester.pumpAndSettle();
    expect(look(), MpEyeLook.down);
    await tester.tap(find.byType(TextField).last);
    await tester.pumpAndSettle();
    expect(look(), MpEyeLook.closed);
  });

  testWidgets('MpEye idle loop runs and stops cleanly on dispose', (
    tester,
  ) async {
    await _pump(tester, const MpEye());
    for (var i = 0; i < 60; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
}
