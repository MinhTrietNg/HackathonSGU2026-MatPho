import 'dart:async';

import 'package:mat_pho/data/models/models.dart';
import 'fake_data.dart';
import 'fake_scenario.dart';

final class FakeWorld {
  FakeWorld(this.scenario) {
    final noCameras = scenario.has(FakeCase.noCameras);
    groups = [
      for (final g in FakeData.groups)
        noCameras ? g.copyWith(cameraCount: 0) : g,
    ];
    cameras = noCameras ? [] : [...FakeData.cameras];
    areas = [...FakeData.areas];
    members = {
      for (final e in FakeData.members.entries) e.key: [...e.value],
    };
    if (scenario.has(FakeCase.alertsOnlyRole)) {
      final sky = FakeData.skyGarden;
      groups = [
        for (final g in groups)
          if (g.id == sky.id)
            Group(
              id: g.id,
              name: g.name,
              myRole: GroupRole.alertsOnly,
              myNickname: g.myNickname,
              cameraCount: g.cameraCount,
              memberCount: g.memberCount,
            )
          else
            g,
      ];
      members[sky.id] = [
        for (final m in members[sky.id]!)
          m.isYou
              ? m.copyWith(
                  role: GroupRole.alertsOnly,
                  cameraIds: [
                    for (final c in cameras)
                      if (c.groupId == sky.id) c.id,
                  ],
                )
              : m,
      ];
    }
    if (!scenario.has(FakeCase.historyEmpty)) {
      events.addAll(FakeData.history());
    }
    signedIn = !scenario.has(FakeCase.signedOut);
  }

  final FakeScenario scenario;
  final _clock = Stopwatch()..start();
  var _nextId = 1;

  User user = FakeData.user;
  String password = FakeData.password;
  late bool signedIn;
  int failedLogins = 0;
  DateTime? lockedUntil;
  int failedOtps = 0;

  bool loudWhenSilent = true;

  final events = <FireEvent>[];
  final _incoming = StreamController<FireEvent>.broadcast();

  final firedCameraIds = <String>{};

  late List<Group> groups;
  late List<Area> areas;
  late List<Camera> cameras;
  late Map<String, List<Member>> members;

  final invitationsWaiting = <Invitation>[];

  final trash = <({TrashedCamera entry, Camera camera})>[];
  static const trashRetention = Duration(days: 30);

  DateTime now() => scenario.freezeClock
      ? scenario.origin
      : scenario.origin.add(_clock.elapsed);

  String newId(String prefix) => '$prefix-${_nextId++}';

  Future<void> delay([Duration base = const Duration(milliseconds: 400)]) =>
      Future.delayed(scenario.scaled(base));

  Stream<FireEvent> get incoming => _incoming.stream;

  void addEvent(FireEvent event, {bool alert = false}) {
    events.insert(0, event);
    if (alert) _incoming.add(event);
  }

  FireEvent event(String id) => events.firstWhere(
    (e) => e.id == id,
    orElse: () => throw StateError('No event $id'),
  );

  void replaceEvent(FireEvent event) {
    final i = events.indexWhere((e) => e.id == event.id);
    events[i] = event;
  }

  Group group(String id) => groups.firstWhere(
    (g) => g.id == id,
    orElse: () => throw StateError('No group $id'),
  );

  void replaceGroup(Group group) {
    final i = groups.indexWhere((g) => g.id == group.id);
    groups[i] = group;
  }

  Member me(String groupId) => members[groupId]!.firstWhere((m) => m.isYou);

  void startNewAccount(User account) {
    user = account;
    final personal = FakeData.personalGroupOf(account);
    groups = [personal];
    members = {
      personal.id: [FakeData.personalMemberOf(account)],
    };
    cameras = [];
    areas = [];
    trash.clear();
    events.clear();
  }

  void dispose() {
    _incoming.close();
  }
}
