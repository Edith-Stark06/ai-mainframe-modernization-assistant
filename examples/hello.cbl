      *=======================================================*
      * hello.cbl                                             *
      * Purpose: Demonstrate DISPLAY and MOVE statements.     *
      *=======================================================*
       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELLO.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-GREETING PIC X(20) VALUE SPACES.
       01 WS-COUNT    PIC 9(3)  VALUE ZEROS.

       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY "HELLO WORLD".
           MOVE "WELCOME" TO WS-GREETING.
           DISPLAY WS-GREETING.
           MOVE 1 TO WS-COUNT.
           STOP RUN.
