"""Sessions J.2/J.3 (Initiatives/multi-language-targets/thread-1-java-target)
-- message-class and gRPC stub generation for the Java target.

Per the codegen-timing decision (histories/gRPC-wiring/
codegen-timing-decision.md), harpia does not shell out to protoc itself for
Java: it stands up a self-contained Gradle project under <dest>/java/, wired
with protobuf-gradle-plugin (+ its grpc plugin, J.3), and the *consumer's*
Gradle build resolves protoc/protoc-gen-grpc-java + generates the message and
stub classes the first time it runs.

Every per-message .proto AND _service.proto is copied in, plus the two
framework protos the service protos import (errorCode/heartBeat -- NOT
capabilities_service, an unrelated whole-project gRPC capability
advertisement out of this session's scope). All of these now carry `option
java_package`/`java_multiple_files` (message protos since J.1; the framework
protos + Service.proto template since J.3 -- see Assets/proto/protofiles/).
<dest>/java/ is deliberately self-contained (no reach outside its own tree
via a relative srcDir) so it can be handed to an Android consumer as its own
Gradle module later (thread README §7). Must run after main.py's
copyBasicProtos, which is what actually populates
<dest>/proto/protofiles/{errorCode,heartBeat}.proto.
"""
import os

from Logger.logger import logger
from Errors.Error import Error, Types, Classes
from Util.util import loadTemplate, write_if_different, copy_if_different

# Named project.gradle.tmpl, not build.gradle.tmpl -- the repo-wide
# .gitignore's `*build*` glob would otherwise silently exclude it from
# version control despite it being source, not a build artifact.
_BUILD_GRADLE_TEMPLATE = loadTemplate(__file__, "project.gradle.tmpl")
_SETTINGS_GRADLE_TEMPLATE = loadTemplate(__file__, "settings.gradle.tmpl")

# Static framework protos the per-message _service.proto imports (see
# Assets/proto/protofiles/Service.proto) -- copied once, not per-message.
_FRAMEWORK_PROTOS = ("errorCode.proto", "heartBeat.proto")


class GradleAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.javaRoot = os.path.join(dest, "java")
        self.protoSrcDir = os.path.join(self.javaRoot, "src", "main", "proto",
                                        "protofiles")
        self.sourceProtoDir = os.path.join(dest, "proto", "protofiles")
        self.log = logger(outFile=None, moduleName="GradleAdapter")

    def _copy(self, fileName):
        srcPath = os.path.join(self.sourceProtoDir, fileName)
        if not os.path.exists(srcPath):
            return False
        copy_if_different(srcPath, os.path.join(self.protoSrcDir, fileName))
        return True

    def Process(self):
        os.makedirs(self.protoSrcDir, exist_ok=True)

        write_if_different(os.path.join(self.javaRoot, "build.gradle"),
                           _BUILD_GRADLE_TEMPLATE)
        write_if_different(os.path.join(self.javaRoot, "settings.gradle"),
                           _SETTINGS_GRADLE_TEMPLATE)

        copied = 0
        for msg in self.messages:
            if self._copy("{}_{}.proto".format(msg.name, msg.md5Hash)):
                copied += 1
            # _service.proto: FileCreator writes one per message regardless
            # of whether the message is table-bearing -- copy unconditionally,
            # same as the message .proto above.
            if self._copy("{}_{}_service.proto".format(msg.name, msg.md5Hash)):
                copied += 1

        for fileName in _FRAMEWORK_PROTOS:
            if self._copy(fileName):
                copied += 1

        if copied == 0:
            self.log.print("no message .proto files to package for the Java target")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.protoSrcDir)

        self.log.print("wired {} .proto file(s) into the Java Gradle project at {}".format(
            copied, self.javaRoot))
        return None
