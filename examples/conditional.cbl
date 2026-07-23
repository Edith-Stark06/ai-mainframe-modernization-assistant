      *=======================================================*
      * conditional.cbl                                       *
      * Purpose: Demonstrate IF / ELSE control flow.          *
      *=======================================================*
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CONDITIONAL.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-SCORE  PIC 9(3) VALUE ZEROS.
       01 WS-GRADE  PIC X(1) VALUE SPACES.

       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE 85 TO WS-SCORE.
           IF WS-SCORE > 80
               MOVE "A" TO WS-GRADE
           ELSE
               MOVE "B" TO WS-GRADE.
           DISPLAY WS-GRADE.
           STOP RUN.
