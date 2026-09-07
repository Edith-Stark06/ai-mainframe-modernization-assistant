       IDENTIFICATION DIVISION.
       PROGRAM-ID. MISLEADNM.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
      * WS-FRAUD-SCORE is only a loop counter, despite its name.
       01 WS-FRAUD-SCORE  PIC 9(3) VALUE 0.
       01 WS-TOTAL        PIC 9(5) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM ADD-ITEMS UNTIL WS-FRAUD-SCORE > 5
           DISPLAY WS-TOTAL
           STOP RUN.
       ADD-ITEMS.
           ADD 10 TO WS-TOTAL
           ADD 1 TO WS-FRAUD-SCORE.
