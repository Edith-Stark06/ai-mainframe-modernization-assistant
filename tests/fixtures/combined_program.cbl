       IDENTIFICATION DIVISION.
       PROGRAM-ID. COMBINED-PROGRAM.
       
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(2) VALUE 10.
       01 WS-B PIC 9(2) VALUE 20.
       
       PROCEDURE DIVISION.
       MAIN-PARAGRAPH.
           MOVE 30 TO WS-A.
           ADD WS-B TO WS-A.
           IF WS-A > 40
               CALL "OVER-LIMIT"
           ELSE
               PERFORM UNTIL WS-B <= 0
                   SUBTRACT 5 FROM WS-B
                   DISPLAY WS-B
               END-PERFORM
           END-IF.
           STOP RUN.
