public class PerformTest {

    private int cnt = 0;

    public static void main(String[] args) {
        new PerformTest().run();
    }

    public void run() {

        subPara();
        return;

    }

    private void subPara() {

        System.out.println(String.format("%02d", cnt));

    }

}
