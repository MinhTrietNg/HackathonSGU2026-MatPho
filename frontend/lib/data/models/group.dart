enum GroupRole {
  owner,

  manager,

  member,

  alertsOnly;

  bool get canManage => this == owner || this == manager;

  bool get canWatch => this != alertsOnly;
}

final class Group {
  const Group({
    required this.id,
    required this.name,
    required this.myRole,
    required this.myNickname,
    required this.cameraCount,
    required this.memberCount,
    this.isPersonal = false,
    this.address,
  });

  final String id;

  final String name;
  final GroupRole myRole;

  final String myNickname;

  final int cameraCount;

  final int memberCount;

  final bool isPersonal;

  final String? address;

  Group copyWith({
    String? name,
    String? myNickname,
    int? cameraCount,
    int? memberCount,
    String? address,
  }) => Group(
    id: id,
    name: name ?? this.name,
    myRole: myRole,
    myNickname: myNickname ?? this.myNickname,
    cameraCount: cameraCount ?? this.cameraCount,
    memberCount: memberCount ?? this.memberCount,
    isPersonal: isPersonal,
    address: address ?? this.address,
  );

  @override
  bool operator ==(Object other) =>
      other is Group &&
      other.id == id &&
      other.name == name &&
      other.myRole == myRole &&
      other.myNickname == myNickname &&
      other.cameraCount == cameraCount &&
      other.memberCount == memberCount &&
      other.isPersonal == isPersonal &&
      other.address == address;

  @override
  int get hashCode => Object.hash(
    id,
    name,
    myRole,
    myNickname,
    cameraCount,
    memberCount,
    isPersonal,
    address,
  );
}

final class Member {
  const Member({
    required this.id,
    required this.phone,
    required this.role,
    this.realName,
    this.nickname,
    this.note,
    this.cameraIds,
    this.isYou = false,
    this.pending = false,
    this.invitedAt,
  });

  final String id;

  final String phone;
  final GroupRole role;

  final String? realName;

  final String? nickname;

  final String? note;

  final List<String>? cameraIds;

  final bool isYou;

  final bool pending;

  final DateTime? invitedAt;

  String get displayName => nickname ?? realName ?? phone;

  Member copyWith({
    GroupRole? role,
    List<String>? cameraIds,
    bool allCameras = false,
    String? nickname,
    bool clearNickname = false,
  }) => Member(
    id: id,
    phone: phone,
    role: role ?? this.role,
    realName: realName,
    nickname: clearNickname ? null : nickname ?? this.nickname,
    note: note,
    cameraIds: allCameras ? null : cameraIds ?? this.cameraIds,
    isYou: isYou,
    pending: pending,
    invitedAt: invitedAt,
  );
}

final class Invitation {
  const Invitation({
    required this.id,
    required this.groupId,
    required this.groupName,
    required this.inviterName,
    required this.role,
    required this.cameraNames,
    this.nickname,
    this.groupAddress,
    this.cameraCount,
    this.memberCount,
    this.createdAt,
  });

  final String id;
  final String groupId;

  final String groupName;

  final String inviterName;
  final GroupRole role;

  final List<String> cameraNames;

  final String? nickname;

  final String? groupAddress;

  final int? cameraCount;

  final int? memberCount;

  final DateTime? createdAt;
}
