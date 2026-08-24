"""Session J.2 (initiatives/multi-language-targets/thread-1-java-target) --
message-class generation for the Java target.

Per the codegen-timing decision (histories/gRPC-wiring/
codegen-timing-decision.md), harpia does not shell out to protoc itself for
Java: it stands up a self-contained Gradle project under <dest>/java/, wired
with protobuf-gradle-plugin, and the *consumer's* Gradle build resolves
protoc + generates the message classes the first time it runs.

Only the plain per-message .proto files are copied in (no gRPC yet -- J.3's
scope, and Service.proto's framework protos (errorCode/heartBeat/
capabilities_service) don't carry `option java_package` yet either, per that
same decision doc). <dest>/java/ is deliberately self-contained (no reach
outside its own tree via a relative srcDir) so it can be handed to an Android
consumer as its own Gradle module later (thread README §7).
"""
import os

from logger.logger import logger
from Errors.Error import Error, Types, Classes
from util.util import loadTemplate, write_if_different, copy_if_different

# Named project.gradle.tmpl, not build.gradle.tmpl -- the repo-wide
# .gitignore's `*build*` glob would otherwise silently exclude it from
# version control despite it being source, not a build artifact.
_BUILD_GRADLE_TEMPLATE = loadTemplate(__file__, "project.gradle.tmpl")
_SETTINGS_GRADLE_TEMPLATE = loadTemplate(__file__, "settings.gradle.tmpl")


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

    def Process(self):
        os.makedirs(self.protoSrcDir, exist_ok=True)

        write_if_different(os.path.join(self.javaRoot, "build.gradle"),
                           _BUILD_GRADLE_TEMPLATE)
        write_if_different(os.path.join(self.javaRoot, "settings.gradle"),
                           _SETTINGS_GRADLE_TEMPLATE)

        copied = 0
        for msg in self.messages:
            fileName = "{}_{}.proto".format(msg.name, msg.md5Hash)
            srcPath = os.path.join(self.sourceProtoDir, fileName)
            if not os.path.exists(srcPath):
                # FileCreator skipped this message for some reason -- nothing
                # to copy, not this adapter's error to raise.
                continue
            copy_if_different(srcPath, os.path.join(self.protoSrcDir, fileName))
            copied += 1

        if copied == 0:
            self.log.print("no message .proto files to package for the Java target")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.protoSrcDir)

        self.log.print("wired {} message .proto(s) into the Java Gradle project at {}".format(
            copied, self.javaRoot))
        return None
