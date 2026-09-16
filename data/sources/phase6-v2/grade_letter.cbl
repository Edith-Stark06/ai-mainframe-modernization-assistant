       IDENTIFICATION DIVISION.
       PROGRAM-ID. GRADELTR.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-SCORE   PIC 9(3) VALUE 0.
       01 WS-GRADE   PIC X VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM ASSIGN-GRADE.
           DISPLAY WS-GRADE.
           STOP RUN.
       ASSIGN-GRADE.
           IF WS-SCORE >= 90
               MOVE 'A' TO WS-GRADE
           ELSE
               IF WS-SCORE >= 80
                   MOVE 'B' TO WS-GRADE
               ELSE
                   IF WS-SCORE >= 70
                       MOVE 'C' TO WS-GRADE
                   ELSE
                       MOVE 'F' TO WS-GRADE
                   END-IF
               END-IF
           END-IF.
