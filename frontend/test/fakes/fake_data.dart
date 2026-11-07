import 'package:mat_pho/data/models/models.dart';

abstract final class FakeData {
  static final demoNow = DateTime(2025, 10, 23, 21, 47, 43);

  static final today = DateTime(2025, 10, 23);
  static final yesterday = DateTime(2025, 10, 22);

  static const user = User(
    id: 'u-minh-anh',
    fullName: 'Nguyễn Minh Anh',
    phone: '0912345678',
  );

  static const password = 'matkhau123';

  static const otpCode = '123456';

  static const otpResendCooldown = Duration(seconds: 60);

  static const testAlertReceivedAfter = Duration(milliseconds: 1200);

  static const fireCameraId = 'cam-charger';

  static const suspectSign = DetectedSign.smoke;
  static const suspectConfidence = 0.61;

  static const imageSentAfter = Duration(milliseconds: 400);

  static const fireConfirmedAfter = Duration(milliseconds: 5100);

  static const fireConfidence = 0.93;

  static const fireNotifiedAfter = Duration(milliseconds: 6800);

  static const notFireConfirmedAfter = Duration(milliseconds: 4600);

  static const dismissalReason = DismissalReason(
    explanation: 'Chỉ là đèn xe chiếu lên tường.',
  );

  static FireEvent fireAlert({
    String id = 'evt-fire',
    String cameraId = fireCameraId,
    DateTime? detectedAt,
  }) => FireEvent(
    id: id,
    cameraId: cameraId,
    locationName: 'Hầm xe',
    status: EventStatus.fire,
    detectedAt: detectedAt ?? DateTime(2025, 10, 23, 21, 47, 31),
    summary: 'Lửa ở xe máy',
    detail: 'Lửa và khói ở xe máy bên trái',
    sign: DetectedSign.fire,
    confidence: fireConfidence,
    checkCount: 2,
    address: 'Hầm B1, chung cư Sky Garden, 12 Nguyễn Văn Linh, Q.7',
    callScript: 'Cháy xe máy ở khu sạc',
    timeline: const [
      TimelineStep(TimelineStepKind.detected, Duration.zero),
      TimelineStep(TimelineStepKind.imageSent, imageSentAfter),
      TimelineStep(TimelineStepKind.confirmedFire, fireConfirmedAfter),
      TimelineStep(TimelineStepKind.notified, fireNotifiedAfter),
    ],
  );

  static FireEvent dismissedEvent({
    String id = 'evt-dismissed',
    String cameraId = fireCameraId,
    DateTime? detectedAt,
  }) => FireEvent(
    id: id,
    cameraId: cameraId,
    locationName: 'Hầm xe',
    status: EventStatus.dismissed,
    detectedAt: detectedAt ?? DateTime(2025, 10, 23, 21, 40, 12),
    summary: 'Đèn xe chiếu lên tường',
    detail: 'AI kiểm tra lại 2 lần, không thấy khói hay lửa.',
    checkCount: 2,
    timeline: const [
      TimelineStep(TimelineStepKind.detected, Duration.zero),
      TimelineStep(TimelineStepKind.confirmedNotFire, notFireConfirmedAfter),
      TimelineStep(TimelineStepKind.notNotified, null),
    ],
  );

  static FireEvent unverifiedEvent({
    String id = 'evt-unverified',
    String cameraId = fireCameraId,
    DateTime? detectedAt,
  }) => FireEvent(
    id: id,
    cameraId: cameraId,
    locationName: 'Hầm xe',
    status: EventStatus.unverified,
    detectedAt: detectedAt ?? DateTime(2025, 10, 22, 19, 2),
    summary: 'Khói mờ ở lối xuống',
    sign: DetectedSign.smoke,
    confidence: suspectConfidence,
    timeline: const [
      TimelineStep(TimelineStepKind.detected, Duration.zero),
      TimelineStep(TimelineStepKind.imageSent, imageSentAfter),
    ],
  );

  static List<FireEvent> history() {
    final fire = fireAlert();
    return [
      fire.copyWith(called114: true, resolved: true),
      dismissedEvent(),
      unverifiedEvent(),
      FireEvent(
        id: 'evt-false-alarm',
        cameraId: fireCameraId,
        locationName: 'Hầm xe',
        status: EventStatus.falseAlarm,
        detectedAt: DateTime(2025, 10, 22, 8, 15),
        summary: 'Hơi nước từ ống xả',
        sign: DetectedSign.smoke,
        confidence: suspectConfidence,
        timeline: const [
          TimelineStep(TimelineStepKind.detected, Duration.zero),
        ],
      ),
    ];
  }

  static const skyGarden = Group(
    id: 'g-sky',
    name: 'Chung cư Sky Garden',
    myRole: GroupRole.owner,
    myNickname: 'Minh Anh',
    cameraCount: 5,
    memberCount: 4,
  );

  static const home = Group(
    id: 'g-home',
    name: 'Nhà mình',
    myRole: GroupRole.owner,
    myNickname: 'Ba',
    cameraCount: 3,
    memberCount: 4,
  );

  static const office = Group(
    id: 'g-office',
    name: 'Văn phòng công ty',
    myRole: GroupRole.member,
    myNickname: 'Minh Anh',
    cameraCount: 2,
    memberCount: 3,
  );

  static final personal = personalGroupOf(user);

  static Group personalGroupOf(User u) => Group(
    id: 'g-personal-${u.id}',
    name: 'Cá Nhân',
    myRole: GroupRole.owner,
    myNickname: u.fullName,
    cameraCount: 0,
    memberCount: 1,
    isPersonal: true,
  );

  static Member personalMemberOf(User u) => Member(
    id: 'm-you-personal-${u.id}',
    phone: u.phone,
    role: GroupRole.owner,
    realName: u.fullName,
    isYou: true,
  );

  static final groups = [skyGarden, home, office, personal];

  static const areas = [
    Area(id: 'a-b1', groupId: 'g-sky', name: 'Hầm B1'),
    Area(id: 'a-b2', groupId: 'g-sky', name: 'Hầm B2'),
    Area(id: 'a-lobby', groupId: 'g-sky', name: 'Sảnh tầng 1'),
    Area(id: 'a-home', groupId: 'g-home', name: 'Trong nhà'),
    Area(id: 'a-office', groupId: 'g-office', name: 'Kho tầng 1'),
  ];

  static const newAreaExample = 'Bãi ô tô ngoài trời';

  static const chargerWatchArea = WatchArea(
    left: 0.06,
    top: 0.41,
    width: 0.47,
    height: 0.46,
  );

  static const probedDeviceName = 'Imou Ranger 2';

  static const rtspExample = 'rtsp://192.168.1.10:554/stream1';

  static final cameras = [
    const Camera(
      id: 'cam-charger',
      groupId: 'g-sky',
      areaId: 'a-b1',
      name: 'Khu sạc xe',
      rtspUrl: rtspExample,
      watchArea: chargerWatchArea,
    ),
    const Camera(
      id: 'cam-ramp',
      groupId: 'g-sky',
      areaId: 'a-b1',
      name: 'Lối lên dốc',
      rtspUrl: 'rtsp://192.168.1.11:554/stream1',
    ),
    Camera(
      id: 'cam-down',
      groupId: 'g-sky',
      areaId: 'a-b2',
      name: 'Lối xuống',
      rtspUrl: 'rtsp://192.168.1.12:554/stream1',
      status: CameraStatus.signalLost,
      signalLostSince: DateTime(2025, 10, 23, 21, 30),
    ),
    ...homeCameras,
    const Camera(
      id: 'cam-store',
      groupId: 'g-office',
      areaId: 'a-office',
      name: 'Kho hàng',
      rtspUrl: 'rtsp://10.0.0.21:554/stream1',
    ),
    const Camera(
      id: 'cam-back',
      groupId: 'g-office',
      areaId: 'a-office',
      name: 'Cửa sau',
      rtspUrl: 'rtsp://10.0.0.22:554/stream1',
    ),
  ];

  static const homeCameras = [
    Camera(
      id: 'cam-living',
      groupId: 'g-home',
      areaId: 'a-home',
      name: 'Phòng khách',
      rtspUrl: 'rtsp://192.168.0.21:554/stream1',
    ),
    Camera(
      id: 'cam-kitchen',
      groupId: 'g-home',
      areaId: 'a-home',
      name: 'Bếp',
      rtspUrl: 'rtsp://192.168.0.22:554/stream1',
    ),
    Camera(
      id: 'cam-front',
      groupId: 'g-home',
      areaId: 'a-home',
      name: 'Cửa trước',
      rtspUrl: 'rtsp://192.168.0.23:554/stream1',
    ),
  ];

  static final registeredPhones = <String>{
    user.phone,
    for (final group in members.values)
      for (final member in group) member.phone,
    '0987654321',
  };

  static const unregisteredPhone = '0911222333';

  static final members = <String, List<Member>>{
    'g-sky': [
      const Member(
        id: 'm-you-sky',
        phone: '0912345678',
        role: GroupRole.owner,
        realName: 'Nguyễn Minh Anh',
        nickname: 'Minh Anh',
        isYou: true,
      ),
      const Member(
        id: 'm-lan',
        phone: '0908000001',
        role: GroupRole.manager,
        realName: 'Phạm Thị Lan',
        note: 'Quản lý toà nhà',
      ),
      const Member(
        id: 'm-tuan',
        phone: '0912000678',
        role: GroupRole.member,
        realName: 'Trần Anh Tuấn',
        nickname: 'Chú Tuấn bảo vệ',
        cameraIds: ['cam-charger', 'cam-ramp', 'cam-down'],
      ),
      Member(
        id: 'm-pending',
        phone: '0903456112',
        role: GroupRole.member,
        nickname: 'Bảo vệ ca đêm',
        cameraIds: const ['cam-charger', 'cam-ramp', 'cam-down'],
        pending: true,
        invitedAt: demoNow.subtract(const Duration(minutes: 10)),
      ),
    ],
    'g-home': [
      const Member(
        id: 'm-you-home',
        phone: '0912345678',
        role: GroupRole.owner,
        realName: 'Nguyễn Minh Anh',
        nickname: 'Ba',
        isYou: true,
      ),
      const Member(
        id: 'm-me',
        phone: '0912000002',
        role: GroupRole.manager,
        nickname: 'Mẹ',
      ),
      const Member(
        id: 'm-bin',
        phone: '0912000003',
        role: GroupRole.alertsOnly,
        nickname: 'Bin (con)',
        cameraIds: ['cam-living', 'cam-kitchen', 'cam-front'],
      ),
      const Member(
        id: 'm-na',
        phone: '0912000004',
        role: GroupRole.member,
        nickname: 'Bé Na (con)',
        cameraIds: ['cam-living'],
      ),
    ],
    'g-office': [
      const Member(
        id: 'm-long',
        phone: '0909000001',
        role: GroupRole.owner,
        nickname: 'Anh Long',
        note: 'Giám đốc',
      ),
      const Member(
        id: 'm-mai',
        phone: '0909000002',
        role: GroupRole.manager,
        nickname: 'Chị Mai',
        note: 'Phụ trách IT',
      ),
      const Member(
        id: 'm-me-office',
        phone: '0912345678',
        role: GroupRole.member,
        realName: 'Nguyễn Minh Anh',
        nickname: 'Minh Anh',
        cameraIds: ['cam-store', 'cam-back'],
        isYou: true,
      ),
    ],
    personal.id: [personalMemberOf(user)],
  };

  static const invitation = Invitation(
    id: 'inv-riverside',
    groupId: 'g-riverside',
    groupName: 'Chung cư Riverside',
    inviterName: 'Chị Hoa',
    role: GroupRole.member,
    cameraNames: ['Hầm B1', 'Hầm B2'],
    nickname: 'Minh Anh tầng 5',
  );
}
