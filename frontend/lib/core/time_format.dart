String formatClock(DateTime t, {bool seconds = true}) {
  String two(int v) => v.toString().padLeft(2, '0');
  final hm = '${two(t.hour)}:${two(t.minute)}';
  return seconds ? '$hm:${two(t.second)}' : hm;
}

String formatStepSeconds(Duration d) {
  final seconds = d.inMilliseconds / 1000;
  final text = seconds >= 10
      ? seconds.round().toString()
      : seconds.toStringAsFixed(1);
  return text.replaceAll('.', ',');
}
