
must be able to be altered afterwards, considering what can be diferentiated:
  more tokens (added functionality), more output types (HTML,react-js, etc)
  other languages not yet supported (Node, rust, python, etc)
  more dabase types (relational, file-based, etc)
  more language-like features (specialized processes, specialized languages, GPU-bound languages)
must be able to be debugged imediatly
logs separated by pertinence
  each part of the process have its own file. They all use the same log system, but, have their own file
  in debug mode all intermediary files are kept
it must be able to be "continued". This means that, if it stop or failed for any reason, it must be able to be continued
  each part of the process has a start and finish markers. This markers are either files, marks in registries or comments in files.
  when a process starts, it must be able to identify its markers and if this markers are older then the file it will process, then it is correct. 
  all the pertinent files are created at folders of the process. Processes that are not related to this one, will have no files in it.
  all files and folders, created by a process, must do so with a unique interface, that will manage the creation and usage of this files and folders. 
    every time a file or folder is created, a registry of this folder is created in a file with pertinent information, such as, when it was created, what process created it and a unique identifier of the process - thread identifier, class name, etc.
    every file saved, modified or generated, is followed by a sha256 of this file. If the sha256 of this file does not mach with the file, than it must be replaced/recalculated/reworked.
    the sha256 is saved in 2 places. The first place is a file that follows the file and has the extention .sha256, and the second place is in the registry
      there is 1 main registry file that will have all the information of the entyre process and one for the pertinent process.
      the registry file contains metadata of the generated file:
        n° of bytes, creation-date, relative-path, sha256, associated version, calculated version.
    
