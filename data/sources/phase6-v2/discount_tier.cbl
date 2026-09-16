       IDENTIFICATION DIVISION.
       PROGRAM-ID. DISCTIER.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-TIER      PIC 9 VALUE 1.
       01 WS-DISCOUNT  PIC 9(3) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM SET-DISCOUNT.
           DISPLAY WS-DISCOUNT.
           STOP RUN.
       SET-DISCOUNT.
           IF WS-TIER >= 3
               MOVE 20 TO WS-DISCOUNT
           ELSE
               IF WS-TIER = 2
                   MOVE 10 TO WS-DISCOUNT
               ELSE
                   MOVE 0 TO WS-DISCOUNT
               END-IF
           END-IF.
