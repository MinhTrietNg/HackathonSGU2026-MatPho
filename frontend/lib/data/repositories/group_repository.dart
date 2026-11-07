import '../models/group.dart';
import '../models/incident.dart';

abstract interface class GroupRepository {
  Future<List<Group>> listGroups();

  Future<Group> createGroup({required String name, String? myNickname});

  Future<List<Member>> listMembers(String groupId);

  Future<Member> inviteMember({
    required String groupId,
    required String phone,
    required GroupRole role,
    required List<String> cameraIds,
    String? nickname,
  });

  Future<List<Invitation>> listMyInvitations();

  Future<Invitation> getInvitation(String invitationId);

  Future<Group> acceptInvitation(String invitationId, {String? nickname});

  Future<void> declineInvitation(String invitationId);

  Future<Member> setRole({
    required String groupId,
    required String memberId,
    required GroupRole role,
  });

  Future<Member> setCameraAccess({
    required String groupId,
    required String memberId,
    required String cameraId,
    required bool enabled,
  });

  Future<void> removeMember({
    required String groupId,
    required String memberId,
  });

  Future<Member> setNickname({
    required String groupId,
    required String memberId,
    String? nickname,
  });

  Future<void> leaveGroup(String groupId);

  Future<void> dissolveGroup(String groupId);

  Future<Group> updateGroup({
    required String groupId,
    String? name,
    String? address,
  });

  Future<void> revokeInvitation({
    required String groupId,
    required String invitationId,
  });

  Future<List<AuditEntry>> listAuditLog(String groupId, {int limit = 50});
}
